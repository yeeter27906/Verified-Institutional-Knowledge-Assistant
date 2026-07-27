"""
Embedding Client for Modal Embedding Service
Features:
- Connection pooling with requests.Session
- Retry logic (1 retry, 0.2s backoff)
- Timeouts (5s connect, 30s read)
- Keep-alive headers
- Async support with httpx
"""

import os
import logging
from typing import List, Optional, Dict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

logger = logging.getLogger(__name__)


class ModalEmbeddingClient:
    """Client for Modal embedding service with connection pooling and retry logic"""
    
    def __init__(self, modal_url: Optional[str] = None):
        """
        Initialize embedding client
        
        Args:
            modal_url: Modal embedding service URL (e.g., https://...modal.run)
                      If not provided, reads from MODAL_URL env variable
        """
        self.modal_url = modal_url or os.getenv("MODAL_URL")
        
        if not self.modal_url:
            raise ValueError("Modal URL not provided and MODAL_URL env variable not set")
        
        # Ensure URL ends without trailing slash
        self.modal_url = self.modal_url.rstrip('/')
        
        # Create session with connection pooling
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=1,  # 1 retry
            backoff_factor=0.2,  # 0.2s backoff
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"]
        )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set keep-alive headers
        self.session.headers.update({
            "Connection": "keep-alive",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        
        # Timeouts
        self.connect_timeout = 5
        self.read_timeout = 30
        
        logger.info(f" ModalEmbeddingClient initialized with URL: {self.modal_url}")
    
    def __call__(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (list of floats) or None if failed
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            # Prepare request payload
            payload = {
                "doc_id": f"doc_{hash(text)}",
                "content": text,
                "metadata": {}
            }
            
            # Make request with timeouts
            response = self.session.post(
                f"{self.modal_url}/embedding/embed",
                json=payload,
                timeout=(self.connect_timeout, self.read_timeout)
            )
            
            # Check response
            response.raise_for_status()
            
            # Parse embeddings
            result = response.json()
            embeddings = result.get("embeddings", [])
            
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            else:
                logger.error("No embeddings returned from service")
                return None
        
        except requests.exceptions.Timeout:
            logger.error("Embedding request timed out")
            return None
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Embedding request failed: {e}")
            return None
        
        except Exception as e:
            logger.error(f"Unexpected error in embedding: {e}")
            return None
    
    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors (or None for failed embeddings)
        """
        embeddings = []
        
        for text in texts:
            embedding = self(text)
            embeddings.append(embedding)
            
            # Brief pause to avoid rate limiting
            time.sleep(0.01)
        
        return embeddings
    
    def health_check(self) -> bool:
        """
        Check if embedding service is healthy
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.modal_url}/embedding/health",
                timeout=(self.connect_timeout, 10)
            )
            
            response.raise_for_status()
            result = response.json()
            
            is_healthy = result.get("status") == "ok"
            
            if is_healthy:
                logger.info(f" Embedding service healthy (dimension: {result.get('embedding_dimension')})")
            else:
                logger.warning("️ Embedding service returned unhealthy status")
            
            return is_healthy
        
        except Exception as e:
            logger.error(f" Health check failed: {e}")
            return False
    
    def close(self):
        """Close session and cleanup resources"""
        self.session.close()
        logger.info(" Embedding client session closed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class AsyncModalEmbeddingClient:
    """Async version of embedding client using httpx"""
    
    def __init__(self, modal_url: Optional[str] = None):
        """
        Initialize async embedding client
        
        Args:
            modal_url: Modal embedding service URL
        """
        self.modal_url = modal_url or os.getenv("MODAL_URL")
        
        if not self.modal_url:
            raise ValueError("Modal URL not provided and MODAL_URL env variable not set")
        
        self.modal_url = self.modal_url.rstrip('/')
        
        # httpx client will be created when needed
        self._client = None
        
        self.connect_timeout = 5
        self.read_timeout = 30
        
        logger.info(f" AsyncModalEmbeddingClient initialized with URL: {self.modal_url}")
    
    async def _get_client(self):
        """Lazy initialization of httpx client"""
        if self._client is None:
            import httpx
            
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self.connect_timeout,
                    read=self.read_timeout
                ),
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20
                )
            )
        
        return self._client
    
    async def __call__(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text (async)
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if failed
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            client = await self._get_client()
            
            payload = {
                "doc_id": f"doc_{hash(text)}",
                "content": text,
                "metadata": {}
            }
            
            response = await client.post(
                f"{self.modal_url}/embedding/embed",
                json=payload
            )
            
            response.raise_for_status()
            
            result = response.json()
            embeddings = result.get("embeddings", [])
            
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            else:
                logger.error("No embeddings returned from service")
                return None
        
        except Exception as e:
            logger.error(f"Async embedding request failed: {e}")
            return None
    
    async def close(self):
        """Close async client"""
        if self._client:
            await self._client.aclose()
            logger.info(" Async embedding client closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
