"""
Document Advocate — An agent that argues for its assigned documents.

WHAT THIS DOES:
Each advocate receives a subset of retrieved documents and constructs
an argument for why those documents best answer the user's query.

HOW IT WORKS:
1. Advocate receives a group of documents
2. Analyzes each document for relevant findings
3. Constructs a coherent argument with citations
4. Reports confidence in its argument

WHY ADVOCATES:
- Forces deep engagement with fewer documents (vs. skimming all)
- Multiple perspectives surface conflicting evidence
- Explicit reasoning about why evidence matters
- Natural audit trail of how answer was derived

USAGE:
    advocate = DocumentAdvocate(group_id="group_1")
    response = await advocate.argue(
        query="Do ACE inhibitors reduce mortality?",
        documents=docs_subset,
    )
"""

import json
import logging
import re
from openai import AsyncOpenAI

from app.config import get_settings
from app.models.schemas import DocumentWithScore
from app.services.debate.models import AdvocateResponse

logger = logging.getLogger(__name__)

ADVOCATE_MODEL = "gpt-4o"

ADVOCATE_SYSTEM_PROMPT = """You are an expert medical researcher acting as an advocate for a specific set of research papers.

YOUR ROLE:
You must argue why YOUR assigned documents provide the best evidence to answer the query. 
Think of yourself as a lawyer for these papers - your job is to make the strongest possible case.

RULES:
1. ONLY use evidence from the documents provided to you
2. Cite every claim using [PMID:xxxxx] format
3. Be specific - quote key statistics, findings, and conclusions
4. Acknowledge limitations in your documents honestly
5. Do NOT make up information or cite documents you weren't given

OUTPUT FORMAT (JSON):
{
    "argument": "Your 2-3 paragraph argument for why these documents answer the query best",
    "key_findings": [
        "Finding 1 with specific data [PMID:xxxxx]",
        "Finding 2 with specific data [PMID:xxxxx]",
        ...
    ],
    "confidence": 0.0-1.0,
    "cited_pmids": ["12345", "67890"]
}

CONFIDENCE SCALE:
- 0.9-1.0: Documents directly and definitively answer the query
- 0.7-0.9: Documents strongly support an answer with good evidence
- 0.5-0.7: Documents provide partial or indirect evidence
- 0.3-0.5: Documents are tangentially related
- 0.0-0.3: Documents don't really address the query"""


def _format_documents_for_advocate(documents: list[DocumentWithScore]) -> str:
    """Format documents for the advocate prompt."""
    formatted = []
    for i, doc in enumerate(documents, 1):
        formatted.append(f"""
=== DOCUMENT {i} ===
PMID: {doc.pmid}
Title: {doc.title}
Journal: {doc.journal or 'Unknown'}
Relevance Score: {doc.relevance_score:.3f}

Abstract:
{doc.abstract}
""")
    return "\n".join(formatted)


class DocumentAdvocate:
    """
    An agent that argues for a specific set of documents.
    
    Each advocate is assigned a subset of retrieved documents and must
    construct the best possible argument for how those documents
    answer the user's query.
    """
    
    def __init__(self, group_id: str):
        """
        Initialize an advocate for a document group.
        
        Args:
            group_id: Identifier for this advocate (e.g., "group_1")
        """
        self.group_id = group_id
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def argue(
        self,
        query: str,
        documents: list[DocumentWithScore],
    ) -> AdvocateResponse:
        """
        Construct an argument for why these documents answer the query.
        
        Args:
            query: The user's medical question
            documents: The documents assigned to this advocate
            
        Returns:
            AdvocateResponse with argument, findings, confidence, and citations
        """
        if not documents:
            return AdvocateResponse(
                group_id=self.group_id,
                documents=documents,
                argument="No documents were assigned to this advocate.",
                key_findings=[],
                confidence=0.0,
                cited_pmids=[],
            )
        
        logger.info(f"Advocate {self.group_id} arguing for {len(documents)} documents")
        
        # Format documents for the prompt
        docs_text = _format_documents_for_advocate(documents)
        available_pmids = [doc.pmid for doc in documents]
        
        user_prompt = f"""QUERY: {query}

YOUR ASSIGNED DOCUMENTS:
{docs_text}

Available PMIDs for citation: {', '.join(available_pmids)}

Construct your argument for why these documents best answer the query.
Return your response as JSON."""

        try:
            response = await self.client.chat.completions.create(
                model=ADVOCATE_MODEL,
                messages=[
                    {"role": "system", "content": ADVOCATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Extract and validate PMIDs
            cited_pmids = result.get("cited_pmids", [])
            # Also extract any PMIDs from the argument text
            argument_pmids = re.findall(r'\[PMID:(\d+)\]', result.get("argument", ""))
            all_cited = list(set(cited_pmids + argument_pmids))
            # Filter to only PMIDs we actually have
            valid_pmids = [p for p in all_cited if p in available_pmids]
            
            return AdvocateResponse(
                group_id=self.group_id,
                documents=documents,
                argument=result.get("argument", ""),
                key_findings=result.get("key_findings", []),
                confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
                cited_pmids=valid_pmids,
            )
            
        except Exception as e:
            logger.error(f"Advocate {self.group_id} failed: {e}")
            return AdvocateResponse(
                group_id=self.group_id,
                documents=documents,
                argument=f"Error generating argument: {str(e)}",
                key_findings=[],
                confidence=0.0,
                cited_pmids=[],
            )


async def create_advocate_response(
    group_id: str,
    query: str,
    documents: list[DocumentWithScore],
) -> AdvocateResponse:
    """Convenience function to create an advocate and get its response."""
    advocate = DocumentAdvocate(group_id)
    return await advocate.argue(query, documents)
