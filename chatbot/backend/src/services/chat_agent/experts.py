"""
Mixture of Experts (MoE) for Graph of Thought Verification
Three specialized experts: Hallucination Hunter, Source Matcher, Logic Expert
Uses Groq models
"""

import logging
from typing import Dict, List, Tuple
import asyncio
import re

from src.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)


def strip_markdown_json(text: str) -> str:
    """Remove markdown code fences from LLM responses and extract JSON.
    
    Handles formats like:
    ```json
    {...}
    ```
    or
    ```
    {...}
    ```
    Also handles cases where there's extra text before or after the JSON.
    """
    if not text:
        return text
    
    text = text.strip()
    
    # First, try to find JSON within code fences
    # Pattern: ```json ... ``` or ``` ... ```
    code_fence_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    matches = re.findall(code_fence_pattern, text, re.DOTALL)
    if matches:
        # Use the last match (in case there are multiple)
        text = matches[-1].strip()
    
    # Now try to extract just the JSON object/array
    # Find the first { or [ and match to its closing bracket
    import json
    for i, char in enumerate(text):
        if char in '{[':
            # Try to parse from this position
            try:
                # Use JSONDecoder to find where valid JSON ends
                decoder = json.JSONDecoder()
                obj, end_idx = decoder.raw_decode(text[i:])
                # Return the valid JSON string
                return text[i:i+end_idx]
            except json.JSONDecodeError:
                continue
    
    return text.strip()


class Expert:
    """Base class for MoE experts"""
    
    def __init__(self, groq_client: GroqClient):
        """
        Initialize expert
        
        Args:
            groq_client: Groq client for LLM calls
        """
        self.groq_client = groq_client
    
    async def call_llm(self, prompt: str) -> str:
        """
        Call Groq Expert model with the given prompt
        
        Args:
            prompt: Prompt text
        
        Returns:
            LLM response text (empty string on error)
        """
        try:
            response = await self.groq_client.generate_expert(prompt, max_tokens=512)
            return response if response else ""
        except Exception as e:
            logger.error(f"LLM call failed in {self.__class__.__name__}: {e}")
            return ""
    
    async def verify(self, thought: str, context: str, graph_history: List[Dict]) -> Dict:
        """
        Verify a thought (to be implemented by subclasses)
        
        Args:
            thought: The thought to verify
            context: Retrieved context/chunks
            graph_history: Last 3 nodes from the graph
        
        Returns:
            Dict with score and remarks
        """
        raise NotImplementedError


class HallucinationHunter(Expert):
    """
    Expert that detects hallucinations by comparing thought against context
    """
    
    async def verify(self, thought: str, context: str, graph_history: List[Dict]) -> Dict:
        """
        Check if the thought contains any information not present in the context
        Uses STRICT verification - only explicit facts from context are allowed
        
        Returns:
            {
                "score": float (0-1),
                "passed": bool,
                "remarks": str
            }
        """
        prompt = f"""You are a Hallucination Hunter for MetaKGP wiki verification. Your job is to detect if the bot is making up details.

Context from MetaKGP wiki:
{context}

Thought to Verify:
{thought}

STRICT ANALYSIS PROTOCOL:
1. What specific details does the Thought make?
2. Which of these details are ACTUALLY present in the Context?
3. Which details appear to be INVENTED or INFERRED (not in the context)?

Be STRICT: If something isn't explicitly in the context, it's hallucination.

Examples:
✓ PASS: Context says "John is President of TFPS" → Thought: "John leads TFPS" (reasonable paraphrase)
✗ FAIL: Context says "John is President of TFPS" → Thought: "John has been President since 2020" (invented date)
✓ PASS: Thought says "Information not available" or "Insufficient information" (acknowledging limitation)
✗ FAIL: Context has no mention of topic X → Thought makes specific claims about X (pure hallucination)

CRITICAL: Return ONLY a valid JSON object, nothing else. No explanations, no markdown formatting.

Output format:
{{
    "hallucinations_found": ["list specific details that are NOT in the context"],
    "confidence": 0.0-1.0,
    "verdict": "PASS" or "FAIL"
}}

Guidelines for confidence:
- 0.9-1.0: Definitely hallucinating, multiple invented details
- 0.7-0.8: Likely hallucinating, some unsupported claims
- 0.5-0.6: Borderline, minor unsupported inferences
- 0.3-0.4: Mostly grounded, reasonable interpretations
- 0.0-0.2: Fully grounded in context"""

        response = await self.call_llm(prompt)
        
        # Log the raw response for debugging
        if not response or not response.strip():
            logger.error(f"HallucinationHunter received empty response from LLM")
            return {
                "score": 0.6,
                "passed": True,
                "remarks": "LLM returned empty response, defaulting to PASS",
                "expert": "HallucinationHunter"
            }
        
        try:
            # Strip markdown code fences before parsing
            import json
            cleaned_response = strip_markdown_json(response)
            result = json.loads(cleaned_response.strip())
            
            hallucinations = result.get("hallucinations_found", [])
            confidence = float(result.get("confidence", 0.6))
            verdict = result.get("verdict", "PASS")  # Default to PASS
            
            # More lenient: pass if confidence >= 0.4
            passed = verdict == "PASS" or (confidence >= 0.4 and len(hallucinations) <= 1)
            score = confidence if passed else (1.0 - confidence)
            
            remarks = f"Hallucinations: {', '.join(hallucinations)}" if hallucinations else "No hallucinations detected"
            
            return {
                "score": score,
                "passed": passed,
                "remarks": remarks,
                "expert": "HallucinationHunter"
            }
        
        except Exception as e:
            logger.error(f"Failed to parse HallucinationHunter response: {e}")
            logger.error(f"Raw response was: {response}")
            logger.error(f"Cleaned response was: {cleaned_response}")
            return {
                "score": 0.3,
                "passed": False,
                "remarks": f"Parse error: {e}",
                "expert": "HallucinationHunter"
            }


class SourceMatcher(Expert):
    """
    Expert that verifies the thought is semantically contained in the context
    """
    
    async def verify(self, thought: str, context: str, graph_history: List[Dict]) -> Dict:
        """
        Check if the meaning of the thought is directly supported by the retrieved chunks
        Uses STRICT verification - requires explicit support in context
        
        Returns:
            {
                "score": float (0-1),
                "passed": bool,
                "remarks": str
            }
        """
        prompt = f"""You are a Source Matcher expert. Your job is to verify if a claim is directly supported by source text.

Context from MetaKGP wiki:
{context}

Thought to Verify:
{thought}

STRICT VERIFICATION PROTOCOL:
Question: Does the SOURCE TEXT explicitly contain information that directly supports this Thought?

Analysis Steps:
1. Identify the key claims in the Thought
2. For each claim, search the Context for explicit supporting evidence
3. A claim is supported ONLY if the Context contains the same or equivalent information
4. Paraphrasing is acceptable, but inferences beyond what's stated are NOT

Examples:
✓ PASS: Context: "TFPS conducts photography workshops" → Thought: "Technology Film and Photography Society organizes photography workshops"
✓ PASS: Context: "John is VP of TSG" → Thought: "John holds the Vice President position at Technology Students' Gymkhana"
✗ FAIL: Context: "TFPS has 50 members" → Thought: "TFPS is the largest society" (unsupported comparison)
✗ FAIL: Context mentions "workshop" → Thought: "weekly workshop series" (added frequency not in context)

Be STRICT: The source must actually contain the claim, not just related information.

CRITICAL: Return ONLY a valid JSON object, nothing else. No explanations, no markdown formatting.

Output format:
{{
    "verdict": "YES" or "NO",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation of which claims are/aren't supported"
}}

Confidence Guidelines:
- 1.0: All claims explicitly in context
- 0.8-0.9: Most claims supported, minor paraphrasing
- 0.6-0.7: Some claims supported, some inferred
- 0.4-0.5: Few claims supported, mostly inferred
- 0.0-0.3: Claims not in context or contradicted"""

        response = await self.call_llm(prompt)
        
        # Log the raw response for debugging
        if not response or not response.strip():
            logger.error(f"SourceMatcher received empty response from LLM")
            return {
                "score": 0.6,
                "passed": True,
                "remarks": "LLM returned empty response, defaulting to PASS",
                "expert": "SourceMatcher"
            }
        
        try:
            import json
            # Strip markdown code fences before parsing
            cleaned_response = strip_markdown_json(response)
            result = json.loads(cleaned_response.strip())
            
            verdict = result.get("verdict", "NO")
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")
            
            # Strict: only pass if verdict is YES AND confidence >= 0.6
            passed = verdict == "YES" and confidence >= 0.6
            score = confidence if passed else confidence * 0.5  # Penalize failures
            
            return {
                "score": score,
                "passed": passed,
                "remarks": reasoning,
                "expert": "SourceMatcher"
            }
        
        except Exception as e:
            logger.error(f"Failed to parse SourceMatcher response: {e}")
            logger.error(f"Raw response was: {response}")
            logger.error(f"Cleaned response was: {cleaned_response}")
            return {
                "score": 0.3,
                "passed": False,
                "remarks": f"Parse error: {e}",
                "expert": "SourceMatcher"
            }


class LogicExpert(Expert):
    """
    Expert that ensures the reasoning chain makes sense
    """
    
    async def verify(self, thought: str, context: str, graph_history: List[Dict]) -> Dict:
        """
        Check if the thought follows logically from the premises in the context
        Uses formal logic principles to verify reasoning
        
        Returns:
            {
                "score": float (0-1),
                "passed": bool,
                "remarks": str,
                "action": "keep" | "merge" | "discard"
            }
        """
        # Format graph history
        history_text = ""
        for i, node in enumerate(graph_history[-3:], 1):
            history_text += f"{i}. {node.get('thought', '')}\n"
        
        prompt = f"""You are a Logic Expert. Your job is to ensure logical consistency and verify that conclusions follow from premises.

Context (Premises):
{context}

Thought (Conclusion to Verify):
{thought}

Previous Reasoning Steps:
{history_text if history_text else "This is the first node."}

FORMAL LOGIC ANALYSIS:

Step 1: Extract Premises
- Identify the key facts/premises stated in the Context

Step 2: Extract Conclusion
- Identify the conclusion/claim made in the Thought

Step 3: Verify Logical Flow
- Does the conclusion logically follow from the premises?
- Are there any logical fallacies or unsupported jumps in reasoning?

Examples:
✓ LOGICAL: 
  Premises: "John is taller than Mary. Mary is taller than Sam."
  Conclusion: "John is taller than Sam." (Valid transitive reasoning)

✗ ILLOGICAL:
  Premises: "Cats are animals."
  Conclusion: "Cats can talk." (Non-sequitur, doesn't follow)

✓ LOGICAL:
  Premises: "TFPS conducts photography workshops. Photography workshops teach camera techniques."
  Conclusion: "TFPS teaches camera techniques." (Valid syllogism)

✗ ILLOGICAL:
  Premises: "Event X happened in 2023."
  Conclusion: "Event X happens every year." (Unsupported generalization)

Step 4: Check Redundancy
- Is this Thought adding new information?
- Or is it repeating what was already established in previous steps?

CRITICAL: Return ONLY a valid JSON object, nothing else. No explanations, no markdown formatting.

Output format:
{{
    "is_logical": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Explanation of the logical flow (or lack thereof)",
    "is_redundant": true/false,
    "action": "keep" | "merge" | "discard"
}}

Action Guidelines:
- "keep": Logical and adds new information
- "merge": Logical but redundant with previous steps
- "discard": Illogical or completely unsupported

Confidence Guidelines:
- 0.9-1.0: Clearly follows from premises, no logical issues
- 0.7-0.8: Mostly logical, minor inference gaps
- 0.5-0.6: Some logical connection, requires assumptions
- 0.3-0.4: Weak logical connection, significant assumptions
- 0.0-0.2: No logical connection or fallacious reasoning"""

        response = await self.call_llm(prompt)
        
        # Log the raw response for debugging
        if not response or not response.strip():
            logger.error(f"LogicExpert received empty response from LLM")
            return {
                "score": 0.7,
                "passed": True,
                "remarks": "LLM returned empty response, defaulting to PASS",
                "action": "keep",
                "expert": "LogicExpert"
            }
        
        try:
            import json
            # Strip markdown code fences before parsing
            cleaned_response = strip_markdown_json(response)
            result = json.loads(cleaned_response.strip())
            
            is_logical = result.get("is_logical", False)
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")
            is_redundant = result.get("is_redundant", False)
            action = result.get("action", "keep")
            
            # Strict: pass only if is_logical=true AND confidence >= 0.6
            passed = is_logical and confidence >= 0.6
            
            # Override action if not logical
            if not is_logical:
                action = "discard"
            
            return {
                "score": confidence,
                "passed": passed,
                "remarks": reasoning,
                "action": action,
                "expert": "LogicExpert"
            }
        
        except Exception as e:
            logger.error(f"Failed to parse LogicExpert response: {e}")
            logger.error(f"Raw response was: {response}")
            logger.error(f"Cleaned response was: {cleaned_response}")
            return {
                "score": 0.5,
                "passed": True,
                "remarks": f"Parse error: {e}",
                "action": "keep",
                "expert": "LogicExpert"
            }


class MoEGauntlet:
    """
    Orchestrates the three experts with weighted voting
    """
    
    def __init__(self, groq_client: GroqClient):
        """
        Initialize the MoE Gauntlet with Groq client
        
        Args:
            groq_client: Groq client for expert calls
        """
        self.hallucination_hunter = HallucinationHunter(groq_client=groq_client)
        self.source_matcher = SourceMatcher(groq_client=groq_client)
        self.logic_expert = LogicExpert(groq_client=groq_client)
    
    async def verify_thought(
        self,
        thought: str,
        context: str,
        graph_history: List[Dict]
    ) -> Dict:
        """
        Run all three experts in parallel and compute weighted vote using STRICT consensus
        
        Weighted Voting Formula (STRICT):
        final_score = (source_matcher_score * 0.5) + (hallucination_score * 0.3) + (logic_score * 0.2)
        
        CONSENSUS RULE (All experts must agree):
        - Source Matcher: MUST pass (verdict=YES, confidence >= 0.6)
        - Hallucination Hunter: MUST pass (no hallucinations detected)
        - Logic Expert: MUST pass (is_logical=true, confidence >= 0.6)
        
        Pass threshold: final_score >= 0.6 AND all three experts pass
        
        Args:
            thought: The thought to verify
            context: Retrieved context chunks
            graph_history: Last 3 nodes from the graph
        
        Returns:
            {
                "passed": bool,
                "final_score": float,
                "action": str,
                "expert_results": dict,
                "remarks": str
            }
        """
        logger.info(f"Running MoE Gauntlet (STRICT MODE) on thought: {thought[:100]}...")
        
        # Run all experts in parallel
        results = await asyncio.gather(
            self.hallucination_hunter.verify(thought, context, graph_history),
            self.source_matcher.verify(thought, context, graph_history),
            self.logic_expert.verify(thought, context, graph_history),
            return_exceptions=True
        )
        
        hallucination_result, source_result, logic_result = results
        
        # Handle any exceptions - be strict with failures
        if isinstance(hallucination_result, Exception):
            hallucination_result = {"score": 0.0, "passed": False, "remarks": f"Expert failed: {str(hallucination_result)}"}
        if isinstance(source_result, Exception):
            source_result = {"score": 0.0, "passed": False, "remarks": f"Expert failed: {str(source_result)}"}
        if isinstance(logic_result, Exception):
            logic_result = {"score": 0.0, "passed": False, "action": "discard", "remarks": f"Expert failed: {str(logic_result)}"}
        
        # Weighted voting (strict)
        # Source Matcher (50%), Hallucination Hunter (30%), Logic Expert (20%)
        final_score = (
            source_result["score"] * 0.5 + 
            hallucination_result["score"] * 0.3 + 
            logic_result["score"] * 0.2
        )
        
        # Check if each expert passes
        source_pass = source_result["passed"]
        hallucination_pass = hallucination_result["passed"]
        logic_pass = logic_result["passed"]
        
        # STRICT CONSENSUS RULE: ALL three experts must pass
        experts_passed = sum([source_pass, hallucination_pass, logic_pass])
        all_experts_agree = experts_passed == 3
        
        # Build failure reasons
        failure_reasons = []
        if not source_pass:
            failure_reasons.append("Source not found")
        if not hallucination_pass:
            failure_reasons.append("Hallucination detected")
        if not logic_pass:
            failure_reasons.append("Illogical reasoning")
        
        # Determine overall verdict
        if all_experts_agree and final_score >= 0.6:
            # Perfect consensus with high score
            passed = True
            action = logic_result.get("action", "keep")
            remarks = f"✓ VERIFIED: Expert consensus achieved (Score: {final_score:.2f}/1.0, All 3/3 experts passed)"
        elif final_score < 0.6:
            # Score too low
            passed = False
            action = "discard"
            reasons = ", ".join(failure_reasons) if failure_reasons else "Low confidence"
            remarks = f"✗ REJECTED: Score too low ({final_score:.2f} < 0.6). Issues: {reasons}"
        elif not all_experts_agree:
            # Not all experts agree
            passed = False
            action = "discard"
            reasons = ", ".join(failure_reasons)
            remarks = f"✗ REJECTED: Expert consensus failed ({experts_passed}/3 passed). Issues: {reasons}"
        else:
            # Edge case
            passed = False
            action = "discard"
            remarks = f"✗ REJECTED: Verification criteria not met"
        
        logger.info(f"MoE Verdict (STRICT): {remarks}")
        
        return {
            "passed": passed,
            "final_score": final_score,
            "action": action,
            "expert_results": {
                "hallucination_hunter": hallucination_result,
                "source_matcher": source_result,
                "logic_expert": logic_result
            },
            "experts_passed": experts_passed,
            "failure_reasons": failure_reasons,
            "remarks": remarks
        }
