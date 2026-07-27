"""
MetaKGP Query Service - Business Logic
Handles semantic search operations over wiki chunks
"""

import logging
import time
from typing import List, Optional, Dict

from src.utils.embedding_client import ModalEmbeddingClient
from src.utils.chroma_client import MetaKGPChromaClient

logger = logging.getLogger(__name__)


class QueryService:
    """Service class for semantic search operations"""
    
    def __init__(self, modal_url: str, chroma_dir: str, collection_name: str = "metakgp_wiki"):
        """
        Initialize the query service
        
        Args:
            modal_url: URL of the Modal embedding service
            chroma_dir: Directory for ChromaDB persistence
            collection_name: Name of the ChromaDB collection
        """
        self.embedding_client = ModalEmbeddingClient(modal_url)
        self.chroma_client = MetaKGPChromaClient(
            persist_dir=chroma_dir,
            collection_name=collection_name
        )
        logger.info(f"QueryService initialized with {self.chroma_client.get_count()} documents")
    
    def get_document_count(self) -> int:
        """Get the total number of documents in the collection"""
        return self.chroma_client.get_count()
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        category_filter: Optional[str] = None
    ) -> Dict:
        """
        Perform semantic search over wiki chunks
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filters: Optional metadata filters for ChromaDB
            category_filter: Optional category filter (applied post-search)
        
        Returns:
            Dict with 'results' (list of results), 'query_time_ms', and 'total_results'
        """
        start_time = time.time()
        
        logger.info(f"Query: {query[:100]}...")
        
        # Generate query embedding
        query_embedding = self.embedding_client(query)
        
        if not query_embedding:
            raise ValueError("Failed to generate query embedding")
        
        logger.info(f"Generated embedding dimension: {len(query_embedding)}")
        
        # Search ChromaDB (get more results if we need to filter by category)
        search_top_k = top_k * 2 if category_filter else top_k
        
        results = self.chroma_client.search(
            query_embedding=query_embedding,
            top_k=search_top_k,
            filters=filters
        )
        
        logger.info(f"ChromaDB returned {len(results['ids'])} results")
        
        # Format results
        search_results = []
        
        for i, chunk_id in enumerate(results["ids"]):
            # Convert distance to similarity score [0, 1]
            distance = results["distances"][i]
            score = 1.0 / (1.0 + distance)  # Inverse distance normalization
            
            # Parse metadata
            raw_metadata = results["metadatas"][i]
            
            # Deserialize arrays
            categories = raw_metadata.get("categories", "").split(",")
            categories = [c.strip() for c in categories if c.strip()]
            
            entities = raw_metadata.get("entities", "").split(",")
            entities = [e.strip() for e in entities if e.strip()]
            
            # Build result dictionary
            result = {
                "chunk_id": chunk_id,
                "text": results["documents"][i],
                "score": score,
                "metadata": {
                    "source_page": raw_metadata.get("source_page", ""),
                    "title": raw_metadata.get("title", ""),
                    "chunk_index": raw_metadata.get("chunk_index", 0),
                    "total_chunks": raw_metadata.get("total_chunks", 0),
                    "categories": categories,
                    "entities": entities,
                    "entity_count": raw_metadata.get("entity_count", 0),
                    "relationship_count": raw_metadata.get("relationship_count", 0)
                }
            }
            
            search_results.append(result)
        
        # Post-process: filter by category if requested
        if category_filter:
            search_results = [
                result for result in search_results
                if category_filter.lower() in [cat.lower() for cat in result["metadata"]["categories"]]
            ]
            # Trim to requested top_k
            search_results = search_results[:top_k]
        
        # Calculate query time
        query_time_ms = (time.time() - start_time) * 1000
        
        logger.info(f"Found {len(search_results)} results in {query_time_ms:.1f}ms")
        
        return {
            "results": search_results,
            "query_time_ms": query_time_ms,
            "total_results": len(search_results)
        }
