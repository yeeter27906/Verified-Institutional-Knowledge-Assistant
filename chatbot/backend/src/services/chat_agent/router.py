"""
Simplified Graph of Thought (GoT) Service Router
FastAPI endpoints for the simplified GoT reasoning service using Llama-4-Scout
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import logging
import os

from src.services.chat_agent.engine import SimplifiedGoTEngine

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/got",
    tags=["graph-of-thought"],
    responses={404: {"description": "Not found"}},
)

# Global engine instance
_got_engine: Optional[SimplifiedGoTEngine] = None


def get_got_engine() -> SimplifiedGoTEngine:
    """Dependency to get the GoT engine instance"""
    if _got_engine is None:
        raise HTTPException(
            status_code=503,
            detail="GoT engine not initialized"
        )
    return _got_engine


def set_got_engine(engine: SimplifiedGoTEngine):
    """Set the global GoT engine instance"""
    global _got_engine
    _got_engine = engine


# Pydantic models
class GoTQueryRequest(BaseModel):
    """Request model for GoT query"""
    query: str = Field(..., description="The question to answer using MetaKGP wiki")


class GoTQueryResponse(BaseModel):
    """Response model for GoT query"""
    query: str
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    chunks_retrieved: int
    verification_passed: bool
    verification_score: Optional[float] = None
    reasoning: Optional[str] = None
    sources: Optional[List[str]] = None
    error: Optional[str] = None


class GraphStatusResponse(BaseModel):
    """Response model for graph status"""
    status: str
    engine_initialized: bool
    model: str
    top_k: int


# API Endpoints

@router.post("/query", response_model=GoTQueryResponse)
async def query_got(
    request: GoTQueryRequest,
    engine: SimplifiedGoTEngine = Depends(get_got_engine)
):
    """
    Process a query using simplified Graph of Thought reasoning with Llama-3.3-70b
    
    Pipeline:
    1. Check if query is relevant to IIT Kharagpur/MetaKGP
    2. Query RAG for top 30 relevant chunks
    3. Analyze chunks using Graph of Thought reasoning
    4. Run single MoE verification round (3 experts)
    5. Generate final answer
    
    Example request:
    ```json
    {
        "query": "What is the hostel allocation process at IIT Kharagpur?"
    }
    ```
    
    The response includes:
    - Final answer
    - Confidence score
    - Verification status
    - Source pages
    """
    try:
        logger.info(f"Received GoT query: {request.query}")
        
        # Process query through simplified GoT engine
        result = await engine.process_query(query=request.query)
        
        return GoTQueryResponse(**result)
    
    except Exception as e:
        logger.error(f"GoT query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )


@router.get("/graph-status", response_model=GraphStatusResponse)
async def graph_status(engine: SimplifiedGoTEngine = Depends(get_got_engine)):
    """
    Get status of the GoT engine
    
    Returns:
    - Engine initialization status
    - Model being used
    - Configuration details
    """
    try:
        return GraphStatusResponse(
            status="ok",
            engine_initialized=True,
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            top_k=engine.top_k
        )
    
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Status check failed: {str(e)}"
        )


@router.get("/health")
async def health():
    """Simple health check"""
    return {"status": "ok", "service": "GoT"}
