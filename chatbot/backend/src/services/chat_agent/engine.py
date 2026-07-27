"""
Simplified Graph of Thought (GoT) Engine with Llama-3.3-70b
Architecture: Query -> Iterative RAG (up to 3 calls) -> GoT on chunks -> Single MoE round -> Final answer
"""

import logging
import asyncio
from typing import Dict, List, Optional
import json
import httpx

from src.services.chat_agent.experts import MoEGauntlet, strip_markdown_json
from src.utils.embedding_client import ModalEmbeddingClient
from src.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)


class SimplifiedGoTEngine:
    """
    Simplified Graph of Thought reasoning engine with Iterative RAG
    Process: Query -> Iterative RAG (max 3 queries) -> Analyze chunks -> Single MoE verification -> Final answer
    """
    
    def __init__(
        self,
        modal_url: str,
        groq_api_key: str,
        query_api_url: str = "http://localhost:8000/query/search",
        top_k: int = 30
    ):
        """
        Initialize the simplified GoT Engine
        
        Args:
            modal_url: Modal embedding service URL
            groq_api_key: Groq API key
            query_api_url: URL for the RAG query API
            top_k: Number of chunks to retrieve from RAG
        """
        self.modal_url = modal_url
        self.groq_api_key = groq_api_key
        self.query_api_url = query_api_url
        self.top_k = top_k
        
        # Initialize components
        self.embedding_client = ModalEmbeddingClient(modal_url)
        self.groq_client = GroqClient(groq_api_key)
        self.moe_gauntlet = MoEGauntlet(self.groq_client)
        
        # HTTP client for API calls
        self.http_client = httpx.AsyncClient(timeout=60.0)
        
        logger.info(f"SimplifiedGoTEngine initialized with top_k={top_k}")
    
    async def query_rag(self, query: str, top_k: Optional[int] = None, filters: Optional[Dict] = None) -> Dict:
        """
        Query the RAG API to get relevant context with optional metadata filters
        
        Args:
            query: Search query
            top_k: Number of results to retrieve (uses self.top_k if not specified)
            filters: Optional metadata filters (e.g., {"source_page": "Page Name"})
        
        Returns:
            Dict with results
        """
        try:
            k = top_k if top_k is not None else self.top_k
            payload = {"query": query, "top_k": k}
            
            if filters:
                payload["filters"] = filters
                logger.info(f"Querying RAG: '{query}' with top_k={k}, filters={filters}")
            else:
                logger.info(f"Querying RAG: '{query}' with top_k={k}")
            
            response = await self.http_client.post(
                self.query_api_url,
                json=payload
            )
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            return {"results": [], "error": str(e)}
    
    async def extract_query_entities(self, query: str) -> Dict:
        """
        Extract entities, keywords, and metadata from the query for targeted RAG searches
        
        Args:
            query: User query
        
        Returns:
            Dict with extracted entities, expanded terms, and suggested source pages
        """
        prompt = f"""You are a query analyzer for IIT Kharagpur MetaKGP wiki. Extract entities and keywords for targeted search.

User Query: {query}

ACRONYM DICTIONARY (expand these):
- TFPS → Technology Film and Photography Society
- TLS → Technology Literary Society
- TSG → Technology Students' Gymkhana
- Gymkhana → Technology Students' Gymkhana
- RP / RP Hall → Rajendra Prasad Hall of Residence
- RK / RK Hall → Radha Krishnan Hall of Residence
- Nehru / Nehru Hall → Nehru Hall of Residence
- Azad / Azad Hall → Azad Hall of Residence
- Patel / Patel Hall → Patel Hall of Residence
- MS → Megnad Saha Hall of Residence
- LLR → Lala Lajpat Rai Hall of Residence
- LBS → Lal Bahadur Shastri Hall of Residence
- MMM → Madan Mohan Malaviya Hall of Residence
- BC Roy → BC Roy Technology Hospital
- SN/IG / SNIG → Sarojini Naidu / Indira Gandhi Hall of Residence
- MT → Mother Teresa Hall of Residence
- SNVH → Sister Nivedita Hall of Residence
- HMC → Hall Management Centre
- VP → Vice President
- GSec → General Secretary
- Sec → Secretary
- SWG → Student Welfare Group
- GC → General Championship
- GC Tech → General Championship (Technology)
- GC SocCult → General Championship (Social and Cultural)
- Inter IIT → Inter IIT Cultural Meet / Inter IIT Sports Meet / Inter IIT Tech Meet
- KGP → Kharagpur / IIT Kharagpur

TASK:
1. Identify main entities (people, places, organizations, events)
2. Expand any acronyms found
3. Extract key concepts (e.g., "alumni", "events", "members")
4. Suggest likely source page names from the wiki (be specific with full names)
5. Generate focused search keywords

Example:
Query: "alumni of RK hall"
Output:
{{
  "entities": ["Radha Krishnan Hall of Residence"],
  "expanded_acronyms": {{"RK hall": "Radha Krishnan Hall of Residence"}},
  "key_concepts": ["alumni", "notable people", "students"],
  "suggested_source_pages": ["Radha Krishnan Hall of Residence"],
  "focused_keywords": ["alumni", "students", "notable", "residents"]
}}

CRITICAL: Return ONLY a valid JSON object, nothing else.

Output format:
{{
  "entities": ["list of main entities with full expanded names"],
  "expanded_acronyms": {{"acronym": "full name"}},
  "key_concepts": ["main concepts from query"],
  "suggested_source_pages": ["likely wiki page names"],
  "focused_keywords": ["specific search terms"]
}}"""

        try:
            response = await self.call_llm(prompt, max_tokens=512)
            
            if not response or not response.strip():
                logger.warning("Empty response from entity extraction")
                return self._fallback_entity_extraction(query)
            
            from src.services.chat_agent.experts import strip_markdown_json
            cleaned_response = strip_markdown_json(response)
            
            if not cleaned_response:
                logger.warning("No valid JSON in entity extraction response")
                return self._fallback_entity_extraction(query)
            
            result = json.loads(cleaned_response)
            logger.info(f"Extracted entities: {result.get('entities', [])}")
            logger.info(f"Suggested source pages: {result.get('suggested_source_pages', [])}")
            return result
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return self._fallback_entity_extraction(query)
    
    def _fallback_entity_extraction(self, query: str) -> Dict:
        """Fallback entity extraction using simple heuristics"""
        # Simple acronym expansion
        acronym_map = {
            "TFPS": "Technology Film and Photography Society",
            "TLS": "Technology Literary Society",
            "TSG": "Technology Students' Gymkhana",
            "Gymkhana": "Technology Students' Gymkhana",
            "RP Hall": "Rajendra Prasad Hall of Residence",
            "RP": "Rajendra Prasad Hall of Residence",
            "RK Hall": "Radha Krishnan Hall of Residence",
            "RK": "Radha Krishnan Hall of Residence",
            "Nehru Hall": "Nehru Hall of Residence",
            "Nehru": "Nehru Hall of Residence",
            "Azad Hall": "Azad Hall of Residence",
            "Azad": "Azad Hall of Residence",
            "Patel Hall": "Patel Hall of Residence",
            "Patel": "Patel Hall of Residence",
            "MS": "Megnad Saha Hall of Residence",
            "LLR": "Lala Lajpat Rai Hall of Residence",
            "LBS": "Lal Bahadur Shastri Hall of Residence",
            "MMM": "Madan Mohan Malaviya Hall of Residence",
            "BC Roy": "BC Roy Technology Hospital",
            "SNIG": "Sarojini Naidu / Indira Gandhi Hall of Residence",
            "SN/IG": "Sarojini Naidu / Indira Gandhi Hall of Residence",
            "MT": "Mother Teresa Hall of Residence",
            "SNVH": "Sister Nivedita Hall of Residence",
            "HMC": "Hall Management Centre",
            "VP": "Vice President",
            "GSec": "General Secretary",
            "Sec": "Secretary",
            "SWG": "Student Welfare Group",
            "GC": "General Championship",
            "GC Tech": "General Championship (Technology)",
            "GC SocCult": "General Championship (Social and Cultural)",
            "Inter IIT": "Inter IIT Meet",
            "KGP": "IIT Kharagpur"
        }
        
        expanded_acronyms = {}
        entities = []
        
        for acronym, full_name in acronym_map.items():
            if acronym.lower() in query.lower():
                expanded_acronyms[acronym] = full_name
                entities.append(full_name)
        
        # Extract simple keywords
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'in', 'at', 'to', 'for', 'on', 'with', 'by', 'from'}
        keywords = [word.strip('?.,!') for word in query.lower().split() if word not in stop_words and len(word) > 2]
        
        return {
            "entities": entities,
            "expanded_acronyms": expanded_acronyms,
            "key_concepts": keywords[:3],
            "suggested_source_pages": entities,
            "focused_keywords": keywords[:5]
        }
    
    async def generate_targeted_rag_queries(self, query: str, entity_info: Dict) -> List[Dict]:
        """
        Generate multiple targeted RAG queries with different strategies
        
        Args:
            query: Original user query
            entity_info: Extracted entity information
        
        Returns:
            List of query configs: [{"query": str, "top_k": int, "filters": dict, "strategy": str}]
        """
        queries = []
        
        # Strategy 1: Filtered search on specific source pages with key concepts
        suggested_pages = entity_info.get("suggested_source_pages", [])
        key_concepts = entity_info.get("key_concepts", [])
        
        for page in suggested_pages[:2]:  # Top 2 suggested pages
            for concept in key_concepts[:2]:  # Top 2 concepts
                queries.append({
                    "query": concept,
                    "top_k": 10,
                    "filters": {"source_page": page},
                    "strategy": f"Filtered: {concept} in {page}"
                })
        
        # Strategy 2: Broad search with full entity names
        entities = entity_info.get("entities", [])
        for entity in entities[:2]:
            queries.append({
                "query": entity,
                "top_k": 15,
                "filters": None,
                "strategy": f"Broad entity: {entity}"
            })
        
        # Strategy 3: Original query (unfiltered)
        queries.append({
            "query": query,
            "top_k": 20,
            "filters": None,
            "strategy": "Original query"
        })
        
        # Strategy 4: Focused keywords without filters (discovery mode)
        focused_keywords = entity_info.get("focused_keywords", [])
        if focused_keywords:
            keyword_query = " ".join(focused_keywords[:3])
            queries.append({
                "query": keyword_query,
                "top_k": 15,
                "filters": None,
                "strategy": f"Keywords: {keyword_query}"
            })
        
        logger.info(f"Generated {len(queries)} targeted RAG queries with different strategies")
        return queries
    
    async def call_llm(self, prompt: str, max_tokens: int = 3072) -> str:
        """
        Call Llama-3.3-70b model
        
        Args:
            prompt: Prompt text
            max_tokens: Maximum tokens
        
        Returns:
            LLM response
        """
        try:
            return await self.groq_client.generate_judge(prompt, max_tokens=max_tokens)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""
    
    async def check_relevance(self, query: str) -> Dict:
        """
        Check if the query is related to IIT Kharagpur/MetaKGP
        Also expands common acronyms before processing
        
        Returns:
            {
                "is_relevant": bool,
                "reasoning": str
            }
        """
        prompt = f"""You are a relevance checker and Query Planner for MetaKGP Wiki (IIT Kharagpur information system).

Question: {query}

STEP 1: ACRONYM EXPANSION
The database does NOT understand acronyms. You MUST expand them using this dictionary:
- TFPS -> Technology Film and Photography Society
- TLS -> Technology Literary Society
- TSG -> Technology Students' Gymkhana
- Gymkhana -> Technology Students' Gymkhana
- RP / RP Hall -> Rajendra Prasad Hall of Residence
- RK / RK Hall -> Radha Krishnan Hall of Residence
- Nehru / Nehru Hall -> Nehru Hall of Residence
- Azad / Azad Hall -> Azad Hall of Residence
- Patel / Patel Hall -> Patel Hall of Residence
- MS -> Megnad Saha Hall of Residence
- LLR -> Lala Lajpat Rai Hall of Residence
- LBS -> Lal Bahadur Shastri Hall of Residence
- MMM -> Madan Mohan Malaviya Hall of Residence
- BC Roy -> BC Roy Technology Hospital
- SN/IG / SNIG -> Sarojini Naidu / Indira Gandhi Hall of Residence
- MT -> Mother Teresa Hall of Residence
- SNVH -> Sister Nivedita Hall of Residence
- HMC -> Hall Management Centre
- VP -> Vice President
- GSec -> General Secretary
- Sec -> Secretary
- SWG -> Student Welfare Group
- GC -> General Championship
- GC Tech -> General Championship (Technology)
- GC SocCult -> General Championship (Social and Cultural)
- Inter IIT -> Inter IIT Cultural Meet / Inter IIT Sports Meet / Inter IIT Tech Meet
- KGP -> Kharagpur / IIT Kharagpur


STEP 2: RELEVANCE CHECK
Determine if this question could be related to IIT Kharagpur. Be LENIENT:
- Academic terms (GPA, CGPA, grades like "2.2", courses, departments)
- Campus life, facilities, hostels, societies, events
- Abbreviations or short queries that might refer to IIT KGP specific things
- Technical terms that could relate to academics or campus activities

Only mark as irrelevant if it's CLEARLY about something else (e.g., "weather in New York", "recipe for pasta", "movie recommendations").

When in doubt, mark as RELEVANT. Short or ambiguous queries should be marked RELEVANT.

CRITICAL: Return ONLY a valid JSON object, nothing else. No explanations, no markdown formatting.

Output format:
{{
    "is_relevant": true/false,
    "expanded_query": "query with acronyms expanded",
    "reasoning": "brief explanation"
}}"""
        
        response = await self.call_llm(prompt, max_tokens=256)
        
        try:
            cleaned_response = strip_markdown_json(response)
            result = json.loads(cleaned_response)
            return result
        except:
            # Default to relevant if parsing fails
            return {"is_relevant": True, "reasoning": "Parse error, proceeding"}
    
    async def generate_followup_queries(self, original_query: str, initial_chunks: List[Dict]) -> List[str]:
        """
        Generate follow-up queries based on initial RAG results
        Uses multi-path reasoning approach to create diverse queries
        
        Args:
            original_query: The original user query
            initial_chunks: Chunks retrieved from the first RAG call
        
        Returns:
            List of follow-up queries (max 2)
        """
        # Analyze initial chunks to understand what information we got
        chunk_summaries = []
        for i, chunk in enumerate(initial_chunks[:5], 1):
            chunk_summaries.append(f"{i}. {chunk['metadata']['title']}: {chunk['text'][:150]}...")
        
        chunks_preview = "\n".join(chunk_summaries)
        
        prompt = f"""You are analyzing search results to generate follow-up queries for deeper information gathering using multi-path reasoning.

Original Query: {original_query}

Initial Retrieved Information (top 5 chunks):
{chunks_preview}

TASK: Generate 1-2 follow-up queries using DIFFERENT REASONING PATHS:

PATH 1 - Direct Expansion:
- If the original query is about events/activities, query for specific event names or details mentioned
- If it's about a society/club, query for specific initiatives, projects, or achievements

PATH 2 - Temporal Context:
- If asking about current/recent information, focus on 2024-2025 timeframe
- Query for historical context if relevant

PATH 3 - Related Entities:
- Extract key entities (people, places, organizations) from chunks
- Generate queries about relationships between these entities

Guidelines:
1. Make queries MORE SPECIFIC than the original
2. Use information from the chunks to create targeted queries
3. Each follow-up should explore a DIFFERENT angle (temporal, specific details, relationships)
4. If chunks already provide comprehensive info, return empty list []
5. Example transformations:
   - "events by SWG" → Path 1: "SWG Hacknight details", Path 2: "SWG workshops 2025"
   - "Who is VP of TFPS?" → Path 1: "Vice President Technology Film and Photography Society", Path 2: "TFPS leadership team 2025"

CRITICAL: Return ONLY a valid JSON object, nothing else. No explanations, no markdown formatting.

Output format:
{{
    "followup_queries": ["query 1", "query 2"],
    "reasoning_paths": ["path type for query 1", "path type for query 2"],
    "reasoning": "why these queries help"
}}"""
        
        try:
            response = await self.call_llm(prompt, max_tokens=512)
            
            # Check if response is empty
            if not response or not response.strip():
                logger.warning("Empty response from LLM for follow-up query generation")
                return []
            
            # Strip markdown and extract JSON
            cleaned_response = strip_markdown_json(response)
            
            if not cleaned_response:
                logger.warning("No valid JSON found in follow-up query response")
                return []
            
            result = json.loads(cleaned_response)
            queries = result.get("followup_queries", [])
            
            # Validate queries are strings
            if not isinstance(queries, list):
                logger.warning(f"Invalid followup_queries format: {type(queries)}")
                return []
            
            # Filter to only string queries
            valid_queries = [q for q in queries if isinstance(q, str) and q.strip()]
            
            logger.info(f"Generated {len(valid_queries)} follow-up queries: {valid_queries}")
            return valid_queries[:2]  # Max 2 follow-up queries
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse follow-up queries JSON: {e}")
            logger.error(f"Raw response: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Failed to generate follow-up queries: {e}")
            return []
    
    async def iterative_rag_retrieval(self, query: str, max_iterations: int = 3) -> Dict:
        """
        Perform iterative RAG retrieval with intelligent multi-strategy queries
        Now uses entity extraction and metadata filtering for targeted searches
        
        Args:
            query: Original user query
            max_iterations: Maximum number of RAG query strategies to execute (default 3)
        
        Returns:
            Dict with aggregated results from all iterations
        """
        all_chunks = []
        seen_texts = set()  # Avoid duplicates
        queries_made = []
        
        # Step 1: Extract entities and generate targeted queries
        logger.info(f"Extracting entities from query: {query}")
        entity_info = await self.extract_query_entities(query)
        
        # Step 2: Generate multiple targeted RAG queries with different strategies
        targeted_queries = await self.generate_targeted_rag_queries(query, entity_info)
        
        # Step 3: Execute targeted queries (up to max_iterations)
        for i, query_config in enumerate(targeted_queries[:max_iterations * 2], start=1):
            strategy = query_config["strategy"]
            rag_query = query_config["query"]
            top_k = query_config["top_k"]
            filters = query_config.get("filters")
            
            logger.info(f"Iteration {i}: Strategy: {strategy}")
            
            queries_made.append({
                "query": rag_query,
                "strategy": strategy,
                "filters": filters
            })
            
            # Execute RAG query with filters
            rag_results = await self.query_rag(rag_query, top_k=top_k, filters=filters)
            
            if rag_results.get("results"):
                new_chunks_count = 0
                for chunk in rag_results["results"]:
                    chunk_text = chunk["text"]
                    if chunk_text not in seen_texts:
                        # Tag chunk with the strategy that found it
                        chunk["discovery_strategy"] = strategy
                        all_chunks.append(chunk)
                        seen_texts.add(chunk_text)
                        new_chunks_count += 1
                
                logger.info(f"Iteration {i}: Added {new_chunks_count} new unique chunks (Total: {len(all_chunks)})")
            else:
                logger.info(f"Iteration {i}: No results from this strategy")
            
            # Early stopping if we have enough diverse chunks
            if len(all_chunks) >= 50:
                logger.info(f"Early stopping: Collected {len(all_chunks)} chunks (target reached)")
                break
        
        # Sort all chunks by score (highest first)
        all_chunks.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"Multi-strategy RAG complete: {len(queries_made)} queries executed, {len(all_chunks)} total unique chunks")
        
        return {
            "results": all_chunks,
            "queries_made": queries_made,
            "total_chunks": len(all_chunks),
            "entity_info": entity_info,
            "error": None
        }
    
    async def analyze_chunks(self, query: str, chunks: List[Dict]) -> str:
        """
        Analyze retrieved chunks using Graph of Thought reasoning with multiple reasoning paths
        
        Args:
            query: Original query
            chunks: List of retrieved chunks from RAG
        
        Returns:
            Analyzed thought/summary from chunks with multiple reasoning paths explored
        """
        # Use top 20 chunks since we now have more diverse data from iterative retrieval
        # This gives us ~10k tokens, still within limits
        chunks_to_analyze = chunks[:20]
        
        # Format chunks with source information
        chunks_text = ""
        for i, chunk in enumerate(chunks_to_analyze, 1):
            chunks_text += f"\n--- Chunk {i} (Score: {chunk['score']:.3f}) ---\n"
            chunks_text += f"Title: {chunk['metadata']['title']}\n"
            chunks_text += f"Source: {chunk['metadata']['source_page']}\n"
            chunks_text += f"Text: {chunk['text']}\n"
        
        prompt = f"""You are analyzing information from the MetaKGP wiki using Graph of Thought (GoT) reasoning with multiple paths.

Sub-Question: {query}

Retrieved Context (top 20 most relevant chunks from iterative search):
{chunks_text}

MULTI-PATH REASONING APPROACH:

PATH 1 - Direct Answer from Primary Context:
- Based ONLY on the highest-scoring chunks (1-3), answer the sub-question directly
- Be specific and cite what the source says
- Format: "According to [Source], [fact]"

PATH 2 - Synthesized Answer from Multiple Contexts:
- Combine information from multiple chunks (1-10)
- Mention which sources support each claim
- Look for consensus across different sources
- Format: "Multiple sources indicate: [fact] (Sources: [list])"

PATH 3 - Temporal-Aware Answer (if applicable):
- If asking about current/recent information (2024-2025), extract ONLY claims marked as current
- Flag any outdated information clearly
- Prioritize most recent data
- Format: "As of 2025, [fact] (Source: [name])"

INSTRUCTIONS:
1. Generate answers using ALL THREE PATHS where applicable
2. For each path, extract specific facts, names, dates, numbers, and details
3. Clearly label which path each piece of information comes from
4. If a path is not applicable (e.g., no temporal data needed), skip it
5. If information is insufficient for any path, state it clearly
6. Prioritize chunks with higher scores as they are more relevant
7. ALWAYS cite your sources using the format: (Source: [title/page])

Provide a comprehensive multi-path analysis:"""
        
        logger.info(f"Analyzing top {len(chunks_to_analyze)} chunks with LLM")
        return await self.call_llm(prompt, max_tokens=2048)
    
    async def generate_final_answer(self, query: str, analysis: str, verification_result: Dict) -> str:
        """
        Generate the final answer based on multi-path analysis and expert verification
        
        Args:
            query: Original query
            analysis: Multi-path analysis from chunks
            verification_result: MoE verification result
        
        Returns:
            Final answer with source citations
        """
        verification_remarks = verification_result.get("remarks", "")
        passed = verification_result.get("passed", False)
        final_score = verification_result.get("final_score", 0.0)
        
        # Extract expert verdicts for transparency
        expert_results = verification_result.get("expert_results", {})
        source_matcher_verdict = expert_results.get("source_matcher", {}).get("passed", False)
        hallucination_verdict = expert_results.get("hallucination_hunter", {}).get("passed", False)
        logic_verdict = expert_results.get("logic_expert", {}).get("passed", False)
        
        prompt = f"""You are synthesizing verified information from the MetaKGP wiki (IIT Kharagpur) using Graph of Thought reasoning.

Original Question: {query}

Multi-Path Analysis from Wiki:
{analysis}

Expert Verification Status (MoE Gauntlet):
- Overall Verdict: {"✓ VERIFIED" if passed else "⚠ NEEDS REVIEW"}
- Final Confidence Score: {final_score:.2f}/1.0
- Source Matcher: {"✓ PASS" if source_matcher_verdict else "✗ FAIL"}
- Hallucination Hunter: {"✓ PASS (No hallucinations)" if hallucination_verdict else "✗ FAIL (Hallucinations detected)"}
- Logic Expert: {"✓ PASS" if logic_verdict else "✗ FAIL"}
- Verification Notes: {verification_remarks}

SYNTHESIS INSTRUCTIONS:
1. Construct a SHORT, DIRECT answer using ONLY verified facts from the analysis
2. If multiple reasoning paths provided the same information, mention the consensus
3. Maintain source citations throughout in format: (Source: [page/title])
4. Prioritize information that passed expert verification
5. If verification flagged issues, be cautious and qualify your statements
6. ONLY include information that directly answers the question asked
7. If information is not available, state this clearly and concisely - do NOT provide tangentially related information
8. Avoid unnecessary background or historical context unless specifically asked
9. Be conversational but concise (2-3 sentences for simple queries)
10. Do not make up information not present in the analysis

Example formats:
- "According to the MetaKGP wiki, [fact] (Source: [page]). This is confirmed by [another source]."
- "Multiple sources indicate that [fact] (Sources: [page1], [page2])."
- "As of 2025, [current fact] (Source: [page])."
- "I don't have enough information to answer this question. The MetaKGP wiki does not contain details about [topic]."

Final Answer:"""
        
        logger.info("Generating final answer")
        return await self.call_llm(prompt, max_tokens=2048)
    
    async def process_query(self, query: str) -> Dict:
        """
        Process a query through the simplified pipeline with iterative RAG
        
        Pipeline:
        1. Iterative RAG retrieval (up to 3 queries for comprehensive data gathering)
        2. Check if query is relevant based on retrieved chunks
        3. Analyze chunks with Graph of Thought reasoning
        4. Run single MoE verification round
        5. Generate final answer
        
        Args:
            query: User query
        
        Returns:
            Dict with final answer and metadata
        """
        logger.info(f"Processing query: {query}")
        
        try:
            # Step 1: Query RAG with iterative retrieval first
            logger.info("Step 1: Querying RAG with iterative retrieval (max 3 iterations)")
            rag_results = await self.iterative_rag_retrieval(query, max_iterations=3)
            
            if not rag_results.get("results"):
                logger.warning("No chunks retrieved from RAG")
                # Only check relevance if we got no chunks
                relevance = await self.check_relevance(query)
                
                if not relevance.get("is_relevant", True):
                    logger.info(f"Query not relevant: {relevance.get('reasoning')}")
                    return {
                        "query": query,
                        "answer": "This question is not related to IIT Kharagpur or MetaKGP. I can only answer questions about IIT Kharagpur campus, academics, facilities, events, societies, and related information from the MetaKGP wiki.",
                        "confidence": 0.0,
                        "chunks_retrieved": 0,
                        "verification_passed": False,
                        "reasoning": relevance.get("reasoning"),
                        "error": None
                    }
                
                # If relevant but no chunks found
                return {
                    "query": query,
                    "answer": "I don't have enough information in the MetaKGP wiki to answer this question. The wiki may not contain details about this topic yet.",
                    "confidence": 0.0,
                    "chunks_retrieved": 0,
                    "verification_passed": False,
                    "reasoning": "No relevant chunks found",
                    "error": rag_results.get("error")
                }
            
            # If we got chunks, skip relevance check (chunks prove relevance)
            chunks = rag_results["results"]
            queries_made = rag_results.get("queries_made", [])
            entity_info = rag_results.get("entity_info", {})
            
            logger.info(f"Retrieved {len(chunks)} unique chunks from {len(queries_made)} multi-strategy queries")
            
            # Log entity extraction results
            if entity_info:
                logger.info(f"Detected entities: {entity_info.get('entities', [])}")
                logger.info(f"Expanded acronyms: {entity_info.get('expanded_acronyms', {})}")
            
            # Format context for MoE
            context_text = "\n\n".join([
                f"[{i+1}] {chunk['text']}" 
                for i, chunk in enumerate(chunks[:10])  # Use top 10 for context
            ])
            
            # Step 2: Analyze chunks with GoT reasoning
            logger.info("Step 2: Analyzing chunks")
            analysis = await self.analyze_chunks(query, chunks)
            
            if not analysis:
                logger.error("Failed to analyze chunks")
                return {
                    "query": query,
                    "answer": "I encountered an error while analyzing the information. Please try again.",
                    "confidence": 0.0,
                    "chunks_retrieved": len(chunks),
                    "verification_passed": False,
                    "reasoning": "Analysis failed",
                    "error": "LLM analysis failed"
                }
            
            # Step 3: Single MoE verification round
            logger.info("Step 3: Running MoE verification")
            verification = await self.moe_gauntlet.verify_thought(
                thought=analysis,
                context=context_text,
                graph_history=[]  # No graph history in simplified version
            )
            
            logger.info(f"Verification result: {verification['remarks']}")
            
            # Step 4: Generate final answer
            logger.info("Step 4: Generating final answer")
            final_answer = await self.generate_final_answer(query, analysis, verification)
            
            if not final_answer:
                logger.error("Failed to generate final answer")
                return {
                    "query": query,
                    "answer": "I encountered an error while generating the answer. Please try again.",
                    "confidence": 0.0,
                    "chunks_retrieved": len(chunks),
                    "verification_passed": verification["passed"],
                    "reasoning": verification["remarks"],
                    "error": "Final answer generation failed"
                }
            
            # Return result
            confidence = verification["final_score"] * 0.9  # Scale down slightly
            
            # Extract query keywords (remove common words)
            query_lower = query.lower()
            common_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'in', 'at', 'to', 'for', 'on', 'with', 'by', 'from', 'what', 'who', 'where', 'when', 'how', 'why', 'which'}
            query_keywords = [word for word in query_lower.split() if word not in common_words and len(word) > 2]
            
            # Filter chunks that have query keywords in source_page or title
            relevant_chunks = []
            for chunk in chunks:
                source_page = chunk["metadata"]["source_page"].lower()
                title = chunk["metadata"]["title"].lower()
                
                # Check if any query keyword appears in source_page or title
                has_keyword = any(keyword in source_page or keyword in title for keyword in query_keywords)
                
                if has_keyword:
                    relevant_chunks.append(chunk)
            
            # If we have relevant chunks, use them; otherwise fall back to top chunks
            chunks_for_sources = relevant_chunks if relevant_chunks else chunks
            
            # Extract unique sources, prioritizing those with query keywords
            unique_sources = []
            seen_sources = set()
            for chunk in chunks_for_sources[:15]:  # Check top 15 relevant chunks
                source = chunk["metadata"]["source_page"]
                if source not in seen_sources and len(unique_sources) < 5:
                    unique_sources.append({
                        "page": source,
                        "score": chunk["score"]
                    })
                    seen_sources.add(source)
            
            # Format sources as list of page names
            source_pages = [s["page"] for s in unique_sources]
            
            # Extract query strategies used (for debugging)
            strategies_used = list(set([q.get("strategy", "Unknown") for q in queries_made]))
            
            return {
                "query": query,
                "answer": final_answer,
                "confidence": confidence,
                "chunks_retrieved": len(chunks),
                "queries_made": queries_made,
                "strategies_used": strategies_used,
                "entity_info": entity_info,
                "verification_passed": verification["passed"],
                "verification_score": verification["final_score"],
                "reasoning": verification["remarks"],
                "sources": source_pages,
                "error": None
            }
        
        except Exception as e:
            logger.error(f"Query processing failed: {e}", exc_info=True)
            return {
                "query": query,
                "answer": "I encountered an error while processing your question. Please try again.",
                "confidence": 0.0,
                "chunks_retrieved": 0,
                "verification_passed": False,
                "reasoning": str(e),
                "error": str(e)
            }
    
    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
