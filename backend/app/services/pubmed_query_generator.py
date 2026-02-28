"""
PubMed Query Generator Service.

WHAT THIS DOES:
Converts natural language medical questions into optimized PubMed search queries.

WHY THIS MATTERS:
PubMed search works best with specific medical terms, MeSH headings, and
structured queries. A user's natural question needs to be transformed
for effective document retrieval.

EXAMPLE:
    Input:  "Do ACE inhibitors reduce mortality in heart failure patients?"
    Output: "ACE inhibitors mortality heart failure randomized controlled trial"

HOW IT WORKS:
1. Sends the question to GPT-4o-mini
2. Asks it to extract key medical concepts and terms
3. Formats them as PubMed search terms
4. Optionally adds study type filters (RCT, meta-analysis, etc.)

USAGE:
    generator = PubMedQueryGenerator()
    search_query = await generator.generate("Does metformin help with weight loss?")
    # Returns: "metformin weight loss obesity clinical trial"
"""

import logging
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Use gpt-4o-mini for query generation (fast, cheap)
QUERY_MODEL = "gpt-4o-mini"

GENERATION_PROMPT = """You are a PubMed search query generator. Your job is to convert a natural language medical question into an effective PubMed search query.

RULES:
1. Extract the key medical concepts from the question
2. Use proper medical terminology (e.g., "myocardial infarction" not just "heart attack")
3. Include relevant synonyms separated by spaces
4. Add study type terms if relevant (randomized controlled trial, meta-analysis, cohort study)
5. Keep the query focused - don't add unrelated terms
6. Output ONLY the search terms, no explanation
7. Do NOT use PubMed advanced syntax (no AND/OR/NOT operators, no field tags)

EXAMPLES:
- "Do ACE inhibitors reduce mortality in heart failure?" → "ACE inhibitors angiotensin converting enzyme mortality survival heart failure clinical trial"
- "What are the side effects of metformin?" → "metformin adverse effects side effects safety tolerability"
- "Is aspirin effective for preventing heart attacks?" → "aspirin acetylsalicylic acid prevention myocardial infarction cardiovascular randomized trial"
- "How does obesity affect diabetes risk?" → "obesity body mass index diabetes mellitus type 2 risk factors epidemiology"

Generate a PubMed search query for the following question:"""


class PubMedQueryGenerator:
    """
    Generates optimized PubMed search queries from natural language questions.
    
    Uses GPT-4o-mini to extract medical concepts and terminology,
    then formats them for effective PubMed searching.
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def generate(self, question: str) -> str:
        """
        Generate a PubMed search query from a natural language question.
        
        Args:
            question: The user's medical question
            
        Returns:
            Optimized PubMed search query string
            
        Example:
            generator = PubMedQueryGenerator()
            query = await generator.generate(
                "Does vitamin D supplementation prevent COVID-19?"
            )
            # Returns: "vitamin D cholecalciferol supplementation COVID-19 
            #           SARS-CoV-2 prevention randomized trial"
        """
        logger.info(f"Generating PubMed query for: '{question}'")
        
        try:
            response = await self.client.chat.completions.create(
                model=QUERY_MODEL,
                messages=[
                    {"role": "system", "content": GENERATION_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.3,  # Low temperature for consistent output
                max_tokens=150,   # Search queries should be concise
            )
            
            search_query = response.choices[0].message.content.strip()
            logger.info(f"Generated PubMed query: '{search_query}'")
            
            return search_query
            
        except Exception as e:
            # If generation fails, fall back to using the question as-is
            logger.error(f"PubMed query generation failed: {e}. Using original question.")
            return question


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def generate_pubmed_query(question: str) -> str:
    """
    Convenience function to generate a PubMed search query.
    
    Example:
        query = await generate_pubmed_query("Does exercise help depression?")
        articles = await fetch_pubmed_articles(query, max_results=50)
    """
    generator = PubMedQueryGenerator()
    return await generator.generate(question)
