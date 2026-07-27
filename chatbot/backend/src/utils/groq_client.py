"""
Groq Client
Client for Groq API with high-performance models
"""

import logging
from typing import List
import asyncio
import os

from groq import Groq

logger = logging.getLogger(__name__)


class GroqClient:
    """
    Client for Groq models
    Uses models with highest RPM for optimal performance
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the Groq client
        
        Args:
            api_key: Groq API key (optional, will use GROQ_API_KEY env var if not provided)
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=self.api_key)
        
        # Using Llama-4-Scout-17b-16e for both judge and expert reasoning
        # meta-llama/llama-4-scout-17b-16e-instruct: High performance model with excellent reasoning
        self.judge_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        
        # For experts (fast verification), use the same model
        self.expert_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        
        logger.info(f"GroqClient initialized with models: judge={self.judge_model}, expert={self.expert_model}")
    
    async def generate_judge(self, prompt: str, max_tokens: int = 2048) -> str:
        """
        Call Groq model for complex reasoning
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
        """
        try:
            logger.info(f"Calling Judge model ({self.judge_model}) with prompt length: {len(prompt)}")
            
            # Run in executor since Groq SDK is sync
            loop = asyncio.get_event_loop()
            
            def _generate():
                completion = self.client.chat.completions.create(
                    model=self.judge_model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.7,
                    max_tokens=max_tokens,
                    top_p=0.9,
                    stream=False
                )
                return completion.choices[0].message.content
            
            text = await loop.run_in_executor(None, _generate)
            logger.info(f"Judge model generated {len(text)} chars")
            return text
            
        except Exception as e:
            logger.error(f"Judge model error: {e}")
            raise
    
    async def generate_expert(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Call Groq model for fast verification
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
        """
        try:
            logger.info(f"Calling Expert model ({self.expert_model}) with prompt length: {len(prompt)}")
            
            # Run in executor since Groq SDK is sync
            loop = asyncio.get_event_loop()
            
            def _generate():
                completion = self.client.chat.completions.create(
                    model=self.expert_model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.7,
                    max_tokens=max_tokens,
                    top_p=0.9,
                    stream=False
                )
                return completion.choices[0].message.content
            
            text = await loop.run_in_executor(None, _generate)
            logger.info(f"Expert model generated {len(text)} chars")
            return text
            
        except Exception as e:
            logger.error(f"Expert model error: {e}")
            raise
    
    async def batch_generate_expert(self, prompts: List[str], max_tokens: int = 1024) -> List[str]:
        """
        Batch generate using Expert model
        
        Args:
            prompts: List of input prompts
            max_tokens: Maximum tokens to generate per prompt
            
        Returns:
            List of generated texts
        """
        try:
            logger.info(f"Batch calling Expert model with {len(prompts)} prompts")
            
            results = []
            for prompt in prompts:
                text = await self.generate_expert(prompt, max_tokens)
                results.append(text)
            
            logger.info(f"Expert model batch generated {len(results)} responses")
            return results
            
        except Exception as e:
            logger.error(f"Expert batch error: {e}")
            raise
