"""
RAG Answer Generator.

WHAT THIS DOES:
Takes a question + retrieved documents → generates an answer with inline citations.
This is the "G" in RAG (Retrieval-Augmented Generation).

HOW IT WORKS:
1. User asks a medical question
2. Retriever finds relevant documents (already done before this service)
3. We format documents into a context string
4. GPT-4o generates an answer citing the sources
5. Output includes [PMID:xxxxx] citations for every claim

CITATION FORMAT:
We use [PMID:12345] format because:
- Easy to parse with regex: \[PMID:\d+\]
- Links to real PubMed articles
- Standard format in medical literature

WHAT THIS SERVICE DOESN'T DO (Trust Layer's job):
- Extract individual claims ← ClaimExtractor
- Verify citations are accurate ← AttributionScorer
- Calculate confidence scores ← ConfidenceCalculator
- Find evidence gaps ← GapDetector

This service just generates the initial answer. The Trust Layer verifies it.

USAGE:
    generator = RAGGenerator()
    answer = await generator.generate(
        question="Do ACE inhibitors reduce mortality?",
        documents=retrieved_docs,
    )
    # Returns: "ACE inhibitors have been shown to reduce mortality [PMID:12345]..."
"""

import logging
from openai import AsyncOpenAI

from app.config import get_settings
from app.models.schemas import DocumentWithScore

logger = logging.getLogger(__name__)

# Model to use for generation
# gpt-4o: Best quality, good for final answers
# gpt-4o-mini: Cheaper, good for claim extraction (Trust Layer)
GENERATION_MODEL = "gpt-4o"

# System prompt that instructs the model how to behave
SYSTEM_PROMPT = """You are a medical AI assistant that provides evidence-based answers.

CRITICAL RULES:
1. Answer ONLY based on the provided evidence. Do not use external knowledge.
2. For EVERY factual claim, cite the source using [PMID:xxxxx] format.
3. If the evidence doesn't support a clear answer, say "Based on the provided evidence, I cannot definitively answer this question."
4. Be concise but thorough. Aim for 2-4 paragraphs.
5. If evidence is conflicting, acknowledge the conflict and cite both sides.

CITATION FORMAT:
- Use [PMID:xxxxx] immediately after each claim
- Example: "ACE inhibitors reduce mortality by 23% [PMID:12345]."
- You can cite multiple sources: "...shown in multiple studies [PMID:12345][PMID:67890]."

STRUCTURE YOUR ANSWER:
1. Direct answer to the question
2. Supporting evidence with citations
3. Any important caveats or limitations"""


class RAGGenerator:
    """
    Generates answers with citations using GPT-4o.
    
    This is a straightforward RAG generator - it takes retrieved documents
    and produces an answer. The Trust Layer (separate services) will then
    verify the claims and citations.
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def generate(
        self,
        question: str,
        documents: list[DocumentWithScore],
    ) -> str:
        """
        Generate an answer with inline citations.
        
        Args:
            question: The user's medical question
            documents: Retrieved documents from the Retriever service
            
        Returns:
            Answer string with [PMID:xxxxx] citations
            
        Example:
            answer = await generator.generate(
                question="Do ACE inhibitors reduce mortality in heart failure?",
                documents=retrieved_docs,
            )
            # Returns something like:
            # "ACE inhibitors have been shown to significantly reduce mortality
            #  in heart failure patients [PMID:12345]. A meta-analysis of 5 
            #  randomized trials demonstrated a 23% reduction in all-cause 
            #  mortality [PMID:67890]..."
        """
        if not documents:
            return "I cannot answer this question because no relevant evidence was found in the database."
        
        # Format documents into context
        context = self._format_context(documents)
        
        # Build the user message
        user_message = f"""EVIDENCE:
{context}

QUESTION:
{question}

Please provide an evidence-based answer with citations."""
        
        logger.info(f"Generating answer for: '{question}' with {len(documents)} documents")
        
        # Call GPT-4o
        response = await self.client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=1000,
        )
        
        answer = response.choices[0].message.content
        logger.info(f"Generated answer: {len(answer)} characters")
        
        return answer
    
    def _format_context(self, documents: list[DocumentWithScore]) -> str:
        """
        Format documents into a context string for the prompt.
        
        Each document is formatted as:
        [PMID:12345] (Relevance: 0.89)
        Title: Effect of ACE inhibitors on mortality...
        Abstract: Background: We conducted a study... Results: ...
        
        ---
        
        This format makes it easy for the model to cite sources.
        """
        formatted_docs = []
        
        for doc in documents:
            # Format each document
            doc_text = f"""[PMID:{doc.pmid}] (Relevance: {doc.relevance_score:.2f})
Title: {doc.title}
Abstract: {doc.abstract}"""
            formatted_docs.append(doc_text)
        
        # Join with separators
        return "\n\n---\n\n".join(formatted_docs)


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def generate_answer(
    question: str,
    documents: list[DocumentWithScore],
) -> str:
    """
    Convenience function to generate an answer.
    
    Example:
        answer = await generate_answer(
            "Do ACE inhibitors help with heart failure?",
            retrieved_documents
        )
    """
    generator = RAGGenerator()
    return await generator.generate(question, documents)
