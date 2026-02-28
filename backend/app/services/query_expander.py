"""
Query Expander Service.

WHAT THIS DOES:
Expands user queries with medical synonyms and related terms to improve retrieval.
This bridges the terminology gap between how users ask questions and how medical
papers describe concepts.

WHY THIS MATTERS:
Users say "heart attack" but papers say "myocardial infarction".
Users say "high blood pressure" but papers say "hypertension".
Without expansion, we miss relevant documents.

EXAMPLE:
    Input:  "Does metformin help with weight loss?"
    Output: "metformin weight loss weight reduction obesity body mass index BMI 
             antidiabetic biguanide metabolic"

HOW IT WORKS:
1. Send query to GPT-4o-mini with medical knowledge
2. Ask it to add synonyms, abbreviations, and related terms
3. Return expanded query for embedding/retrieval

USAGE:
    expander = QueryExpander()
    expanded = await expander.expand("Does aspirin prevent heart attacks?")
    # Returns: "aspirin acetylsalicylic acid ASA prevent heart attack 
    #           myocardial infarction MI cardiovascular prevention antiplatelet"
"""

import logging
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Use gpt-4o-mini for expansion (fast, cheap, good enough for this task)
EXPANSION_MODEL = "gpt-4o-mini"

EXPANSION_PROMPT = """You are a medical query expansion system. Your job is to generate ADDITIONAL synonyms, abbreviations, and related terms for a user's medical question to improve search results.

RULES:
1. Output ONLY the additional expansion terms (the original query will be prepended automatically)
2. Add medical synonyms (e.g., for "heart attack" add "myocardial infarction")
3. Add common abbreviations (e.g., for "ACE inhibitors" add "angiotensin-converting enzyme")
4. Add related clinical terms that papers might use
5. Do NOT repeat the original query terms
6. Do NOT add unrelated terms
7. Return ONLY the expansion terms, no explanation

EXAMPLES:
- "Does aspirin prevent heart attacks?" → "acetylsalicylic acid ASA myocardial infarction MI cardiovascular prevention antiplatelet therapy"
- "metformin weight loss" → "weight reduction obesity body mass index BMI antidiabetic biguanide metabolic syndrome"
- "high blood pressure treatment" → "hypertension antihypertensive therapy medication management systolic diastolic BP"

Generate expansion terms for the following query:"""


class QueryExpander:
    """
    Expands queries with medical synonyms and related terms.
    
    Pipeline position:
    Query → [QueryExpander] → Expanded Query → Retriever → Documents → ...
    
    This runs BEFORE retrieval to improve document matching.
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def expand(self, query: str) -> str:
        """
        Expand a query with medical synonyms and related terms.
        
        The original query is ALWAYS included at the start to preserve
        the user's intent and context.
        
        Args:
            query: The original user query
            
        Returns:
            Expanded query string: "{original query} {additional terms}"
            
        Example:
            expander = QueryExpander()
            expanded = await expander.expand("Does metformin help with weight loss?")
            # Returns: "Does metformin help with weight loss? metformin weight reduction obesity BMI..."
        """
        logger.info(f"Expanding query: '{query}'")
        
        try:
            response = await self.client.chat.completions.create(
                model=EXPANSION_MODEL,
                messages=[
                    {"role": "system", "content": EXPANSION_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0.3,  # Low temperature for consistent expansions
                max_tokens=200,   # Expansions don't need to be long
            )
            
            expansion_terms = response.choices[0].message.content.strip()
            
            # Always prepend the original query to ensure it's included
            # This preserves the user's exact intent while adding synonyms
            expanded = f"{query} {expansion_terms}"
            
            logger.info(f"Expanded query: '{expanded[:100]}...'")
            
            return expanded
            
        except Exception as e:
            # If expansion fails, fall back to original query
            logger.error(f"Query expansion failed: {e}. Using original query.")
            return query


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def expand_query(query: str) -> str:
    """
    Convenience function to expand a query.
    
    Example:
        expanded = await expand_query("heart attack prevention")
        docs = await retrieve_documents(expanded, db)
    """
    expander = QueryExpander()
    return await expander.expand(query)
