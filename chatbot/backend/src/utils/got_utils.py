"""
Graph of Thought (GoT) Utilities
NetworkX serialization, Pyvis visualization, semantic caching
"""

import json
import logging
import math
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import networkx as nx
from pyvis.network import Network
import chromadb
from chromadb.config import Settings

from src.utils.embedding_client import ModalEmbeddingClient

logger = logging.getLogger(__name__)


class GoTCache:
    """
    Semantic cache for verified thoughts using ChromaDB
    """
    
    def __init__(self, chroma_dir: str, embedding_client: ModalEmbeddingClient):
        """
        Initialize the GoT cache
        
        Args:
            chroma_dir: Directory for ChromaDB persistence
            embedding_client: Modal embedding client for generating embeddings
        """
        self.embedding_client = embedding_client
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create the verified thoughts collection
        self.collection = self.client.get_or_create_collection(
            name="verified_thoughts",
            metadata={"hnsw:space": "cosine"}
        )
        
        logger.info(f"GoT Cache initialized with {self.collection.count()} verified thoughts")
    
    def check_cache(self, query: str, threshold: float = 0.1) -> Optional[Dict]:
        """
        Check if a similar thought exists in the cache
        
        Args:
            query: The sub-query or thought to check
            threshold: Distance threshold (< 0.1 means very similar)
        
        Returns:
            Cached result dict if found, None otherwise
        """
        # Generate embedding for query
        query_embedding = self.embedding_client(query)
        
        if not query_embedding:
            return None
        
        # Search in cache collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=1
        )
        
        if not results['ids'] or len(results['ids'][0]) == 0:
            return None
        
        # Check distance threshold
        distance = results['distances'][0][0]
        
        if distance < threshold:
            logger.info(f"Cache HIT! Distance: {distance:.4f}")
            return {
                "thought": results['documents'][0][0],
                "sources": json.loads(results['metadatas'][0][0].get('sources', '[]')),
                "verification_score": results['metadatas'][0][0].get('verification_score', 0.0),
                "cached": True
            }
        
        logger.info(f"Cache MISS. Distance: {distance:.4f}")
        return None
    
    def add_to_cache(self, thought: str, sources: List[str], verification_score: float):
        """
        Add a verified thought to the cache
        
        Args:
            thought: The verified thought text
            sources: List of source URLs
            verification_score: Verification score from MoE
        """
        # Generate embedding
        embedding = self.embedding_client(thought)
        
        if not embedding:
            logger.error("Failed to generate embedding for thought")
            return
        
        # Generate unique ID
        thought_id = f"thought_{self.collection.count() + 1:06d}"
        
        # Add to collection
        self.collection.add(
            ids=[thought_id],
            embeddings=[embedding],
            documents=[thought],
            metadatas=[{
                "sources": json.dumps(sources),
                "verification_score": verification_score
            }]
        )
        
        logger.info(f"Added thought to cache: {thought_id}")


class NetworkXManager:
    """
    Manages NetworkX graph serialization and operations
    """
    
    @staticmethod
    def create_graph() -> nx.DiGraph:
        """Create a new directed graph for GoT"""
        return nx.DiGraph()
    
    @staticmethod
    def add_node(
        graph: nx.DiGraph,
        node_id: str,
        thought: str,
        sources: List[str],
        parent_nodes: List[str],
        verification_score: float,
        expert_remarks: str = ""
    ) -> nx.DiGraph:
        """
        Add a node to the graph
        
        Args:
            graph: NetworkX DiGraph
            node_id: Unique node identifier
            thought: The thought/reasoning text
            sources: List of source URLs
            parent_nodes: List of parent node IDs
            verification_score: Verification score from MoE
            expert_remarks: Optional remarks from experts
        
        Returns:
            Updated graph
        """
        graph.add_node(
            node_id,
            thought=thought,
            sources=sources,
            parent_nodes=parent_nodes,
            verification_score=verification_score,
            expert_remarks=expert_remarks
        )
        
        # Add edges from parents
        for parent_id in parent_nodes:
            if parent_id in graph.nodes:
                graph.add_edge(parent_id, node_id)
        
        return graph
    
    @staticmethod
    def merge_nodes(graph: nx.DiGraph, node_id: str, parent_id: str) -> nx.DiGraph:
        """
        Merge a redundant node with its parent
        
        Args:
            graph: NetworkX DiGraph
            node_id: Node to merge
            parent_id: Parent node to merge into
        
        Returns:
            Updated graph
        """
        if node_id in graph.nodes and parent_id in graph.nodes:
            # Merge thoughts
            parent_thought = graph.nodes[parent_id].get('thought', '')
            node_thought = graph.nodes[node_id].get('thought', '')
            graph.nodes[parent_id]['thought'] = f"{parent_thought}\n\n{node_thought}"
            
            # Merge sources
            parent_sources = set(graph.nodes[parent_id].get('sources', []))
            node_sources = set(graph.nodes[node_id].get('sources', []))
            graph.nodes[parent_id]['sources'] = list(parent_sources | node_sources)
            
            # Remove redundant node
            graph.remove_node(node_id)
            
            logger.info(f"Merged node {node_id} into {parent_id}")
        
        return graph
    
    @staticmethod
    def to_json(graph: nx.DiGraph) -> str:
        """
        Serialize graph to JSON
        
        Args:
            graph: NetworkX DiGraph
        
        Returns:
            JSON string
        """
        data = nx.node_link_data(graph)
        return json.dumps(data, indent=2)
    
    @staticmethod
    def from_json(json_str: str) -> nx.DiGraph:
        """
        Deserialize graph from JSON
        
        Args:
            json_str: JSON string
        
        Returns:
            NetworkX DiGraph
        """
        data = json.loads(json_str)
        return nx.node_link_graph(data, directed=True)
    
    @staticmethod
    def get_best_path(graph: nx.DiGraph, start_node: str, end_node: str) -> List[str]:
        """
        Get the best path between two nodes based on verification scores
        
        Args:
            graph: NetworkX DiGraph
            start_node: Starting node ID
            end_node: Ending node ID
        
        Returns:
            List of node IDs in the best path
        """
        try:
            # Weight edges inversely by verification score (lower weight = better)
            for u, v in graph.edges():
                score = graph.nodes[v].get('verification_score', 0.5)
                graph[u][v]['weight'] = 1.0 / (score + 0.01)  # Avoid division by zero
            
            # Find shortest path (which is best path with our weighting)
            path = nx.shortest_path(graph, start_node, end_node, weight='weight')
            return path
        
        except nx.NetworkXNoPath:
            logger.warning(f"No path found between {start_node} and {end_node}")
            return []


class PyvisVisualizer:
    """
    Converts NetworkX graph to interactive Pyvis HTML
    """
    
    @staticmethod
    def generate_html(graph: nx.DiGraph, output_path: Optional[str] = None) -> str:
        """
        Generate interactive HTML visualization of the graph
        
        Args:
            graph: NetworkX DiGraph
            output_path: Optional path to save HTML file
        
        Returns:
            HTML string
        """
        # Create Pyvis network
        net = Network(
            height="750px",
            width="100%",
            directed=True,
            bgcolor="#222222",
            font_color="white"
        )
        
        # Set physics layout
        net.barnes_hut(
            gravity=-8000,
            central_gravity=0.3,
            spring_length=200,
            spring_strength=0.001,
            damping=0.09
        )
        
        # Add nodes with styling based on verification score
        for node_id in graph.nodes():
            node_data = graph.nodes[node_id]
            thought = node_data.get('thought', '')
            score = node_data.get('verification_score', 0.0)
            sources = node_data.get('sources', [])
            
            # Color based on verification score
            if score >= 0.9:
                color = "#00ff00"  # Green
            elif score >= 0.7:
                color = "#ffff00"  # Yellow
            else:
                color = "#ff0000"  # Red
            
            # Create hover title with details
            title = f"<b>{node_id}</b><br>"
            title += f"Score: {score:.2f}<br>"
            title += f"<br><i>{thought[:200]}...</i><br>"
            if sources:
                title += f"<br>Sources: {len(sources)}"
            
            net.add_node(
                node_id,
                label=f"{node_id}\n{score:.2f}",
                title=title,
                color=color,
                size=20 + (score * 30)
            )
        
        # Add edges
        for u, v in graph.edges():
            net.add_edge(u, v)
        
        # Generate HTML
        if output_path:
            net.save_graph(output_path)
            with open(output_path, 'r') as f:
                html = f.read()
        else:
            html = net.generate_html()
        
        return html
