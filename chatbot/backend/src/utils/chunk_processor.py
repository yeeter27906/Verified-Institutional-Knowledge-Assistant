"""
Wiki Chunk Processor
Processes wiki pages into chunks with entity extraction and relationship mapping
"""

import hashlib
import re
from typing import List, Dict
import spacy
import logging

logger = logging.getLogger(__name__)


class WikiChunkProcessor:
    """Process wiki pages into chunks with entities and relationships"""
    
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        """
        Initialize chunk processor
        
        Args:
            chunk_size: Target chunk size in words
            chunk_overlap: Overlap between chunks in words
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Load spaCy model for entity extraction
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logger.info(" Loaded spaCy model: en_core_web_sm")
        except OSError:
            logger.warning("️ spaCy model not found, downloading...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
            self.nlp = spacy.load("en_core_web_sm")
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Input text
            
        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []
        
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk = ' '.join(chunk_words)
            
            if chunk.strip():
                chunks.append(chunk)
            
            # Stop if we've reached the end
            if i + self.chunk_size >= len(words):
                break
        
        return chunks
    
    def extract_entities(self, text: str, max_entities: int = 50) -> List[str]:
        """
        Extract named entities using spaCy
        
        Args:
            text: Input text
            max_entities: Maximum number of entities to extract
            
        Returns:
            List of unique entity strings
        """
        if not text:
            return []
        
        try:
            # Truncate very long texts to avoid memory issues
            text_sample = text[:10000]
            doc = self.nlp(text_sample)
            
            # Extract unique entities
            entities = []
            seen = set()
            
            for ent in doc.ents:
                entity_text = ent.text.strip()
                if entity_text and entity_text.lower() not in seen:
                    entities.append(entity_text)
                    seen.add(entity_text.lower())
                
                if len(entities) >= max_entities:
                    break
            
            return entities
        
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []
    
    def extract_wiki_links(
        self,
        wiki_links: List[str],
        chunk_text: str,
        max_links: int = 20
    ) -> List[str]:
        """
        Filter wiki links that appear in chunk text
        
        Args:
            wiki_links: All wiki links from page
            chunk_text: Current chunk text
            max_links: Maximum links to return
            
        Returns:
            List of relevant wiki links
        """
        if not wiki_links:
            return []
        
        chunk_lower = chunk_text.lower()
        relevant_links = []
        
        for link in wiki_links:
            # Normalize link (replace underscores with spaces)
            normalized_link = link.replace('_', ' ').lower()
            
            # Check if link appears in chunk
            if normalized_link in chunk_lower or link.lower() in chunk_lower:
                relevant_links.append(link)
            
            if len(relevant_links) >= max_links:
                break
        
        return relevant_links
    
    def build_relationships(
        self,
        entities: List[str],
        wiki_links: List[str],
        max_relationships: int = 30
    ) -> List[Dict[str, str]]:
        """
        Build entity relationships from co-occurrence and wiki links
        
        Args:
            entities: Extracted named entities
            wiki_links: Relevant wiki links
            max_relationships: Maximum relationships to create
            
        Returns:
            List of relationship dictionaries
        """
        relationships = []
        
        # 1. Entity co-occurrence relationships (entities that appear together)
        for i, ent1 in enumerate(entities[:10]):  # Limit to top 10 entities
            for ent2 in entities[i+1:i+6]:  # Max 5 relationships per entity
                relationships.append({
                    "from": ent1,
                    "to": ent2,
                    "type": "co_occurs_with"
                })
                
                if len(relationships) >= max_relationships:
                    return relationships
        
        # 2. Entity to wiki-link relationships
        for link in wiki_links[:10]:  # Top 10 wiki links
            for entity in entities[:5]:  # Top 5 entities
                relationships.append({
                    "from": entity,
                    "to": link,
                    "type": "mentioned_in_page"
                })
                
                if len(relationships) >= max_relationships:
                    return relationships
        
        return relationships
    
    def process_page(
        self,
        page_name: str,
        title: str,
        cleaned_text: str,
        categories: List[str],
        links: List[str]
    ) -> List[Dict]:
        """
        Process a wiki page into chunks with metadata
        
        Args:
            page_name: Unique page identifier
            title: Display title
            cleaned_text: Cleaned page content
            categories: Page categories
            links: Wiki links from page
        
        Returns:
            List of chunk dictionaries in required format:
            {
                "chunk_id": "unique_id",
                "text": "chunk content",
                "metadata": {
                    "source_page": "page_name",
                    "title": "page_title",
                    "categories": ["cat1", "cat2"],
                    "chunk_index": 0,
                    "total_chunks": 5
                },
                "entities": ["entity1", "entity2"],
                "relationships": [{"from": "e1", "to": "e2", "type": "related"}]
            }
        """
        if not cleaned_text or not cleaned_text.strip():
            logger.debug(f"Skipping empty page: {page_name}")
            return []
        
        # Split into chunks
        chunks = self.chunk_text(cleaned_text)
        total_chunks = len(chunks)
        
        if total_chunks == 0:
            return []
        
        processed_chunks = []
        
        for idx, chunk_text in enumerate(chunks):
            try:
                # Generate unique chunk ID (deterministic hash)
                chunk_id_source = f"{page_name}_{idx}_{chunk_text[:100]}"
                chunk_id = hashlib.sha256(chunk_id_source.encode()).hexdigest()[:16]
                
                # Extract entities from this chunk
                entities = self.extract_entities(chunk_text, max_entities=20)
                
                # Filter relevant wiki links for this chunk
                relevant_links = self.extract_wiki_links(links, chunk_text, max_links=15)
                
                # Build relationships
                relationships = self.build_relationships(
                    entities,
                    relevant_links,
                    max_relationships=25
                )
                
                # Build chunk object
                chunk_obj = {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "source_page": page_name,
                        "title": title,
                        "categories": categories or [],
                        "chunk_index": idx,
                        "total_chunks": total_chunks
                    },
                    "entities": entities,
                    "relationships": relationships
                }
                
                processed_chunks.append(chunk_obj)
            
            except Exception as e:
                logger.error(f"Failed to process chunk {idx} of {page_name}: {e}")
                continue
        
        logger.debug(f"Processed {page_name}: {len(processed_chunks)} chunks")
        return processed_chunks
