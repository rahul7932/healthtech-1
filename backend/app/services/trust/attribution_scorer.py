"""
Attribution Scorer Service.

WHAT THIS DOES:
For each claim, determines which documents support, contradict, or are neutral.
This creates the "evidence map" — linking claims to their supporting evidence.

WHY THIS MATTERS:
The RAG generator might cite a document, but does that document ACTUALLY support the claim?
This service verifies the citations by checking if the evidence matches the claim.

SCORING:
- SUPPORTS (+1): Document clearly supports the claim
- CONTRADICTS (-1): Document clearly contradicts the claim  
- NEUTRAL (0): Document mentions related topics but doesn't clearly support/contradict

EXAMPLE:
    Claim: "ACE inhibitors reduce mortality"
    
    Document A (PMID:12345): "Our study found a 23% reduction in mortality with ACE inhibitors"
    → SUPPORTS
    
    Document B (PMID:67890): "ACE inhibitors showed no significant effect on mortality"
    → CONTRADICTS
    
    Document C (PMID:11111): "ACE inhibitors are commonly used in heart failure"
    → NEUTRAL

BATCH PROCESSING:
We batch claim-document pairs to minimize API calls.
Instead of one call per pair, we send multiple pairs in one request.

USAGE:
    scorer = AttributionScorer()
    scored_claims = await scorer.score(claims, documents)
"""

import json
import logging
from typing import Literal

from openai import AsyncOpenAI

from app.config import get_settings
from app.models.schemas import DocumentWithScore, EvidenceReference
from app.services.trust.claim_extractor import ExtractedClaim

logger = logging.getLogger(__name__)

# Use gpt-4o-mini for scoring (cheaper, sufficient for this task)
SCORING_MODEL = "gpt-4o-mini"

SCORING_PROMPT = """You are an evidence evaluation system. Your job is to determine if a document supports, contradicts, or is neutral to a claim.

DEFINITIONS:
- SUPPORTS: The document provides evidence that the claim is true
- CONTRADICTS: The document provides evidence that the claim is false
- NEUTRAL: The document doesn't clearly support or contradict (mentions related topics, but no direct evidence)

Be strict:
- Only mark SUPPORTS if there's clear positive evidence
- Only mark CONTRADICTS if there's clear negative evidence
- When in doubt, mark NEUTRAL

OUTPUT FORMAT (JSON):
{
  "evaluations": [
    {
      "claim_index": 0,
      "doc_pmid": "12345",
      "verdict": "supports",
      "reasoning": "Brief explanation"
    }
  ]
}

Evaluate the following claim-document pairs:"""


# Type alias for verdict
Verdict = Literal["supports", "contradicts", "neutral"]


class ScoredClaim:
    """A claim with its evidence attribution scores."""
    
    def __init__(
        self,
        claim: ExtractedClaim,
        supporting_docs: list[EvidenceReference],
        contradicting_docs: list[EvidenceReference],
        neutral_docs: list[EvidenceReference],
    ):
        self.claim = claim
        self.supporting_docs = supporting_docs
        self.contradicting_docs = contradicting_docs
        self.neutral_docs = neutral_docs
    
    @property
    def support_score(self) -> float:
        """
        Calculate a support score for this claim.
        
        Formula: (supporting - contradicting) / total
        Range: -1 (all contradict) to +1 (all support)
        """
        total = len(self.supporting_docs) + len(self.contradicting_docs) + len(self.neutral_docs)
        if total == 0:
            return 0.0
        return (len(self.supporting_docs) - len(self.contradicting_docs)) / total


class AttributionScorer:
    """
    Scores claim-document pairs to build an evidence map.
    
    Pipeline position:
    Answer → ClaimExtractor → Claims → [AttributionScorer] → ScoredClaims → ...
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def score(
        self,
        claims: list[ExtractedClaim],
        documents: list[DocumentWithScore],
    ) -> list[ScoredClaim]:
        """
        Score each claim against all documents.
        
        Args:
            claims: Extracted claims from the answer
            documents: Retrieved documents used for the answer
            
        Returns:
            List of ScoredClaim objects with evidence attribution
            
        Example:
            scorer = AttributionScorer()
            scored = await scorer.score(claims, documents)
            for sc in scored:
                print(f"{sc.claim.text}: {len(sc.supporting_docs)} supporting")
        """
        if not claims or not documents:
            return [
                ScoredClaim(claim, [], [], [])
                for claim in claims
            ]
        
        logger.info(f"Scoring {len(claims)} claims against {len(documents)} documents")
        
        # Build the evaluation request
        eval_request = self._build_eval_request(claims, documents)
        
        # Call OpenAI
        response = await self.client.chat.completions.create(
            model=SCORING_MODEL,
            messages=[
                {"role": "system", "content": SCORING_PROMPT},
                {"role": "user", "content": eval_request},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        
        # Parse response
        try:
            result = json.loads(response.choices[0].message.content)
            evaluations = result.get("evaluations", [])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse attribution response: {e}")
            evaluations = []
        
        # Build ScoredClaim objects
        scored_claims = self._build_scored_claims(claims, documents, evaluations)
        
        logger.info(f"Scored {len(scored_claims)} claims")
        return scored_claims
    
    def _build_eval_request(
        self,
        claims: list[ExtractedClaim],
        documents: list[DocumentWithScore],
    ) -> str:
        """Build the evaluation request string for the LLM."""
        parts = []
        
        # List claims
        parts.append("CLAIMS:")
        for i, claim in enumerate(claims):
            parts.append(f"[{i}] {claim.text}")
        
        parts.append("\nDOCUMENTS:")
        for doc in documents:
            parts.append(f"[PMID:{doc.pmid}] {doc.title}")
            # Truncate abstract to save tokens
            abstract = doc.abstract[:500] + "..." if len(doc.abstract) > 500 else doc.abstract
            parts.append(f"Abstract: {abstract}\n")
        
        parts.append("\nEvaluate each claim against each document.")
        
        return "\n".join(parts)
    
    def _build_scored_claims(
        self,
        claims: list[ExtractedClaim],
        documents: list[DocumentWithScore],
        evaluations: list[dict],
    ) -> list[ScoredClaim]:
        """Convert LLM evaluations into ScoredClaim objects."""
        # Create a lookup for documents by PMID
        doc_lookup = {doc.pmid: doc for doc in documents}
        
        # Initialize scored claims
        scored_claims = []
        for claim in claims:
            scored_claims.append(ScoredClaim(
                claim=claim,
                supporting_docs=[],
                contradicting_docs=[],
                neutral_docs=[],
            ))
        
        # Process evaluations
        for eval_item in evaluations:
            claim_idx = eval_item.get("claim_index", 0)
            pmid = str(eval_item.get("doc_pmid", ""))
            verdict = eval_item.get("verdict", "neutral").lower()
            
            # Validate indices
            if claim_idx >= len(claims) or pmid not in doc_lookup:
                continue
            
            doc = doc_lookup[pmid]
            evidence_ref = EvidenceReference(
                pmid=doc.pmid,
                title=doc.title,
                relevance_score=doc.relevance_score,
            )
            
            # Add to appropriate list
            scored_claim = scored_claims[claim_idx]
            if verdict == "supports":
                scored_claim.supporting_docs.append(evidence_ref)
            elif verdict == "contradicts":
                scored_claim.contradicting_docs.append(evidence_ref)
            else:
                scored_claim.neutral_docs.append(evidence_ref)
        
        return scored_claims


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def score_claims(
    claims: list[ExtractedClaim],
    documents: list[DocumentWithScore],
) -> list[ScoredClaim]:
    """
    Convenience function to score claims against documents.
    """
    scorer = AttributionScorer()
    return await scorer.score(claims, documents)
