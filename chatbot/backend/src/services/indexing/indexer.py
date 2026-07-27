#!/usr/bin/env python3
"""
MetaKGP Wiki Indexer Service
PostgreSQL → Chunk → Embed → ChromaDB
"""

import argparse
import logging
import os
import pickle
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.utils.embedding_client import ModalEmbeddingClient
from src.utils.chunk_processor import WikiChunkProcessor
from src.utils.chroma_client import MetaKGPChromaClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MetaKGPIndexer:
    """Indexer service for MetaKGP wiki pages"""
    
    def __init__(
        self,
        db_url: str,
        modal_url: str,
        chroma_dir: str = "./chroma_data",
        cache_dir: str = "./cache",
        batch_size: int = 100,
        embedding_batch_size: int = 30,
        reset_offset: bool = False
    ):
        """
        Initialize MetaKGP indexer
        
        Args:
            db_url: PostgreSQL connection URL
            modal_url: Modal embedding service URL
            chroma_dir: ChromaDB persistence directory
            cache_dir: Cache directory for embeddings and offset
            batch_size: Number of pages to fetch per batch
            embedding_batch_size: Number of chunks to embed at once
            reset_offset: Reset offset and reindex from beginning
        """
        self.db_url = db_url
        self.batch_size = batch_size
        self.embedding_batch_size = embedding_batch_size
        
        # Initialize components
        logger.info(" Initializing MetaKGP Indexer...")
        
        self.embedding_client = ModalEmbeddingClient(modal_url)
        self.chunk_processor = WikiChunkProcessor(chunk_size=512, chunk_overlap=50)
        self.chroma_client = MetaKGPChromaClient(
            persist_dir=chroma_dir,
            collection_name="metakgp_wiki"
        )
        
        # Cache setup
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.embedding_cache_file = self.cache_dir / "embeddings.pkl"
        self.offset_file = self.cache_dir / "last_processed_id.txt"
        
        # Load embedding cache
        self.embedding_cache: Dict[str, List[float]] = self._load_embedding_cache()
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Reset offset if requested
        if reset_offset and self.offset_file.exists():
            logger.warning(" Resetting offset - will reindex from beginning")
            self.offset_file.unlink()
        
        # Statistics
        self._pages_processed = 0
        self._chunks_indexed = 0
        self._start_time = time.time()
        
        logger.info(" Indexer initialized successfully")
    
    def _load_embedding_cache(self) -> Dict[str, List[float]]:
        """Load embedding cache from disk"""
        if self.embedding_cache_file.exists():
            try:
                with open(self.embedding_cache_file, 'rb') as f:
                    cache = pickle.load(f)
                logger.info(f" Loaded {len(cache)} cached embeddings")
                return cache
            except Exception as e:
                logger.warning(f"️ Could not load embedding cache: {e}")
        return {}
    
    def _save_embedding_cache(self):
        """Save embedding cache to disk"""
        try:
            with open(self.embedding_cache_file, 'wb') as f:
                pickle.dump(self.embedding_cache, f)
            logger.info(
                f" Saved {len(self.embedding_cache)} embeddings to cache "
                f"(hits: {self._cache_hits}, misses: {self._cache_misses})"
            )
        except Exception as e:
            logger.error(f" Failed to save embedding cache: {e}")
    
    def _get_last_processed_id(self) -> int:
        """Get last processed page ID from offset file"""
        if self.offset_file.exists():
            try:
                id_str = self.offset_file.read_text().strip()
                return int(id_str) if id_str else 0
            except Exception as e:
                logger.warning(f"️ Could not read offset file: {e}")
        return 0
    
    def _save_last_processed_id(self, page_id: int):
        """Save last processed page ID to offset file"""
        try:
            self.offset_file.write_text(str(page_id))
        except Exception as e:
            logger.error(f" Failed to save offset: {e}")
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding with caching
        
        Uses first 200 characters as cache key for deterministic lookups
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if failed
        """
        # Use first 200 chars as cache key
        cache_key = text[:200]
        
        # Check cache
        if cache_key in self.embedding_cache:
            self._cache_hits += 1
            return self.embedding_cache[cache_key]
        
        # Cache miss - call Modal API
        self._cache_misses += 1
        embedding = self.embedding_client(text)
        
        if embedding:
            self.embedding_cache[cache_key] = embedding
            return embedding
        
        logger.error("Failed to generate embedding")
        return None
    
    def _fetch_pages_batch(
        self,
        engine,
        last_id: int
    ) -> List[Dict]:
        """
        Fetch next batch of pages from PostgreSQL
        
        Args:
            engine: SQLAlchemy engine
            last_id: Last processed page ID
            
        Returns:
            List of page dictionaries
        """
        try:
            with engine.connect() as conn:
                query = text("""
                    SELECT 
                        id,
                        name,
                        title,
                        cleaned_text,
                        categories,
                        links
                    FROM metakgp_pages
                    WHERE id > :last_id
                        AND exists = true
                        AND redirect = false
                        AND cleaned_text IS NOT NULL
                        AND cleaned_text != ''
                    ORDER BY id ASC
                    LIMIT :batch_size
                """)
                
                result = conn.execute(
                    query,
                    {"last_id": last_id, "batch_size": self.batch_size}
                )
                
                pages = [dict(row._mapping) for row in result]
                return pages
        
        except Exception as e:
            logger.error(f" Failed to fetch pages: {e}")
            return []
    
    def index_batch(self, pages: List[Dict]):
        """
        Process and index a batch of pages
        
        Pipeline:
        1. Chunk pages with entity extraction
        2. Generate embeddings (with caching)
        3. Add to ChromaDB
        
        Args:
            pages: List of page dictionaries from database
        """
        if not pages:
            return
        
        logger.info(f" Processing {len(pages)} pages...")
        
        # Step 1: Process pages into chunks
        all_chunk_objects = []
        
        for page in pages:
            try:
                chunks = self.chunk_processor.process_page(
                    page_name=page["name"],
                    title=page["title"] or page["name"],
                    cleaned_text=page["cleaned_text"] or "",
                    categories=page["categories"] or [],
                    links=page["links"] or []
                )
                all_chunk_objects.extend(chunks)
            except Exception as e:
                logger.error(f" Failed to process page {page['name']}: {e}")
        
        if not all_chunk_objects:
            logger.warning("️ No chunks generated from batch")
            return
        
        logger.info(
            f"️ Generated {len(all_chunk_objects)} chunks "
            f"from {len(pages)} pages"
        )
        
        # Step 2: Generate embeddings
        chunk_ids = []
        texts = []
        embeddings = []
        successful_chunks = []
        
        for chunk_obj in all_chunk_objects:
            try:
                # Get embedding (with cache)
                embedding = self._get_embedding(chunk_obj["text"])
                
                if embedding:
                    chunk_ids.append(chunk_obj["chunk_id"])
                    texts.append(chunk_obj["text"])
                    embeddings.append(embedding)
                    successful_chunks.append(chunk_obj)
                else:
                    logger.warning(f"️ Skipping chunk {chunk_obj['chunk_id']} - no embedding")
            
            except Exception as e:
                logger.error(f" Failed to embed chunk: {e}")
        
        logger.info(f" Generated {len(embeddings)} embeddings")
        
        # Step 3: Add to ChromaDB
        if chunk_ids:
            try:
                self.chroma_client.add_chunks(
                    chunk_ids=chunk_ids,
                    texts=texts,
                    embeddings=embeddings,
                    chunk_objects=successful_chunks
                )
                self._chunks_indexed += len(chunk_ids)
            except Exception as e:
                logger.error(f" Failed to add chunks to ChromaDB: {e}")
        
        # Update statistics
        self._pages_processed += len(pages)
        
        # Save cache periodically
        if self._pages_processed % 10 == 0:
            self._save_embedding_cache()
    
    def _print_stats(self):
        """Print indexing statistics"""
        elapsed = time.time() - self._start_time
        
        logger.info("=" * 60)
        logger.info(" Indexing Statistics:")
        logger.info(f"   Pages processed: {self._pages_processed}")
        logger.info(f"   Chunks indexed: {self._chunks_indexed}")
        logger.info(f"   Cache hits: {self._cache_hits}")
        logger.info(f"   Cache misses: {self._cache_misses}")
        if self._cache_hits + self._cache_misses > 0:
            hit_rate = 100 * self._cache_hits / (self._cache_hits + self._cache_misses)
            logger.info(f"   Cache hit rate: {hit_rate:.1f}%")
        logger.info(f"   Elapsed time: {elapsed:.1f}s")
        logger.info(f"   Total docs in ChromaDB: {self.chroma_client.get_count()}")
        logger.info("=" * 60)
    
    def run(self):
        """Main indexing loop"""
        logger.info(" Starting indexing service")
        logger.info(f" Database: {self.db_url.split('@')[-1]}")  # Hide credentials
        
        engine = create_engine(self.db_url)
        last_id = self._get_last_processed_id()
        
        logger.info(f" Starting from page ID: {last_id}")
        
        try:
            iteration = 0
            
            while True:
                iteration += 1
                
                # Fetch next batch
                pages = self._fetch_pages_batch(engine, last_id)
                
                if not pages:
                    logger.info(" No more pages to index")
                    self._print_stats()
                    logger.info(" Sleeping for 60s before checking for new pages...")
                    time.sleep(60)
                    continue
                
                logger.info(
                    f"\n{'='*60}\n"
                    f"Iteration {iteration}: Fetched {len(pages)} pages "
                    f"(IDs {pages[0]['id']} - {pages[-1]['id']})\n"
                    f"{'='*60}"
                )
                
                # Process batch
                self.index_batch(pages)
                
                # Update offset
                last_id = pages[-1]["id"]
                self._save_last_processed_id(last_id)
                
                # Print periodic stats
                if iteration % 5 == 0:
                    self._print_stats()
                
                # Brief pause between batches
                time.sleep(2)
        
        except KeyboardInterrupt:
            logger.info("\n⏹️ Stopping indexer (Ctrl+C)")
        
        except Exception as e:
            logger.error(f" Fatal error: {e}", exc_info=True)
        
        finally:
            # Save cache and print final stats
            self._save_embedding_cache()
            self._print_stats()


def main():
    """Main entry point"""
    # Load environment variables from team_2 root directory
    env_path = Path(__file__).resolve().parents[5] / '.env'  # Go up to team_2/
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded .env from {env_path}")
    else:
        # Fallback to default behavior
        load_dotenv()
        logger.warning(f".env not found at {env_path}, using default load_dotenv()")
    
    # Construct DATABASE_URL from environment variables
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_sslmode = os.getenv("DB_SSLMODE", "require")
    
    # Build connection URL
    if db_host and db_name and db_user and db_password:
        db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?sslmode={db_sslmode}"
    else:
        # Fallback to DATABASE_URL if individual components not provided
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("Database configuration missing. Set DB_HOST, DB_NAME, DB_USER, DB_PASSWORD or DATABASE_URL")
    
    parser = argparse.ArgumentParser(
        description="MetaKGP Wiki Indexer Service",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--db-url",
        default=db_url,
        help="PostgreSQL connection URL (e.g., postgresql://user:pass@host:5432/dbname)"
    )
    parser.add_argument(
        "--modal-url",
        default=os.getenv("MODAL_URL"),
        help="Modal embedding service URL (e.g., https://...modal.run)"
    )
    parser.add_argument(
        "--chroma-dir",
        default=os.getenv("CHROMA_DIR", "./chroma_data"),
        help="ChromaDB persistence directory"
    )
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("CACHE_DIR", "./cache"),
        help="Cache directory for embeddings and offset tracking"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of pages to fetch per batch"
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=30,
        help="Number of chunks to embed in parallel"
    )
    parser.add_argument(
        "--reset-offset",
        action="store_true",
        help="Reset offset and reindex from beginning"
    )
    
    args = parser.parse_args()
    
    # Create indexer
    indexer = MetaKGPIndexer(
        db_url=args.db_url,
        modal_url=args.modal_url,
        chroma_dir=args.chroma_dir,
        cache_dir=args.cache_dir,
        batch_size=args.batch_size,
        embedding_batch_size=args.embedding_batch_size,
        reset_offset=args.reset_offset
    )
    
    # Run
    indexer.run()


if __name__ == "__main__":
    main()
