"""
Evidence Gap Detector Service.

WHAT THIS DOES:
Identifies what clinically relevant information is MISSING from the evidence.
This is what makes doctors trust (or distrust) AI recommendations.

WHY THIS MATTERS:
An answer can be "correct" based on available evidence but still be incomplete.
A good medical AI should acknowledge what it DOESN'T know.

GAP CATEGORIES:
- Population: Age groups, demographics not covered
- Dosage: Optimal dosing not specified
- Duration: Long-term effects unknown
- Safety: Side effects, contraindications unclear
- Comparators: No comparison with alternative treatments

EXAMPLE:
    Claim: "ACE inhibitors reduce mortality in heart failure"
    
    Supporting evidence covers:
    - Adults 40-70 years old
    - Short-term outcomes (1-2 years)
    
    Gaps detected:
    - "Pediatric population not addressed"
    - "Long-term outcomes (>5 years) unknown"
    - "Comparison with ARBs not evaluated"

USAGE:
    detector = GapDetector()
    gaps = await detector.detect(claims, documents)
"""

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import get_settings
from app.models.schemas import DocumentWithScore
from app.services.trust.attribution_scorer import ScoredClaim

logger = logging.getLogger(__name__)

# Use gpt-4o-mini for gap detection
GAP_MODEL = "gpt-4o-mini"

GAP_DETECTION_PROMPT = """You are a medical evidence analyst. Your job is to identify gaps in the evidence — what important clinical information is NOT addressed.

THINK LIKE A DOCTOR: What would a clinician want to know that isn't covered?

GAP CATEGORIES:
1. Population gaps: Age groups, demographics, comorbidities not covered
2. Dosage gaps: Optimal dosing, titration, formulations not specified  
3. Duration gaps: Long-term effects, treatment duration unclear
4. Safety gaps: Side effects, contraindications, interactions not addressed
5. Comparator gaps: No comparison with alternative treatments
6. Outcome gaps: Important outcomes not measured (quality of life, etc.)

RULES:
- Be specific: "Pediatric patients under 12" not just "some patients"
- Be relevant: Only clinically important gaps
- Don't repeat gaps already mentioned
- Limit to 3-5 most important gaps per claim

OUTPUT FORMAT (JSON):
{
  "claim_gaps": [
    {
      "claim_index": 0,
      "gaps": ["Specific gap 1", "Specific gap 2"]
    }
  ],
  "global_gaps": ["Gaps that apply to the answer as a whole"]
}

Analyze the following claims and their supporting evidence:"""


@dataclass
class GapResult:
    """Gaps detected for a claim."""
    claim_index: int
    claim_text: str
    gaps: list[str]


class GapDetector:
    """
    Detects missing evidence and uncertainties.
    
    This service identifies what the evidence DOESN'T cover,
    which is crucial for responsible medical AI.
    
    Pipeline position:
    Answer → ClaimExtractor → AttributionScorer → ConfidenceCalc → [GapDetector] → TrustReport
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def detect(
        self,
        scored_claims: list[ScoredClaim],
        documents: list[DocumentWithScore],
    ) -> tuple[list[GapResult], list[str]]:
        """
        Detect evidence gaps for each claim and globally.
        
        Args:
            scored_claims: Claims with attribution scores
            documents: Retrieved documents
            
        Returns:
            Tuple of:
            - List of GapResult for each claim
            - List of global gaps (apply to whole answer)
        """
        if not scored_claims:
            return [], []
        
        logger.info(f"Detecting gaps for {len(scored_claims)} claims")
        
        # Build the analysis request
        request = self._build_request(scored_claims, documents)
        
        # Call OpenAI
        response = await self.client.chat.completions.create(
            model=GAP_MODEL,
            messages=[
                {"role": "system", "content": GAP_DETECTION_PROMPT},
                {"role": "user", "content": request},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        
        # Parse response
        try:
            result = json.loads(response.choices[0].message.content)
            claim_gaps_data = result.get("claim_gaps", [])
            global_gaps = result.get("global_gaps", [])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse gap detection response: {e}")
            return [], []
        
        # Build GapResult objects
        gap_results = []
        for gap_data in claim_gaps_data:
            idx = gap_data.get("claim_index", 0)
            if idx < len(scored_claims):
                gap_results.append(GapResult(
                    claim_index=idx,
                    claim_text=scored_claims[idx].claim.text,
                    gaps=gap_data.get("gaps", []),
                ))
        
        # Ensure we have a GapResult for each claim
        for i, scored_claim in enumerate(scored_claims):
            if not any(gr.claim_index == i for gr in gap_results):
                gap_results.append(GapResult(
                    claim_index=i,
                    claim_text=scored_claim.claim.text,
                    gaps=[],
                ))
        
        # Sort by claim index
        gap_results.sort(key=lambda x: x.claim_index)
        
        logger.info(
            f"Detected gaps: {sum(len(gr.gaps) for gr in gap_results)} claim-specific, "
            f"{len(global_gaps)} global"
        )
        
        return gap_results, global_gaps
    
    def _build_request(
        self,
        scored_claims: list[ScoredClaim],
        documents: list[DocumentWithScore],
    ) -> str:
        """Build the gap detection request."""
        parts = []
        
        parts.append("CLAIMS AND THEIR SUPPORTING EVIDENCE:\n")
        
        for i, scored_claim in enumerate(scored_claims):
            parts.append(f"[Claim {i}]: {scored_claim.claim.text}")
            
            if scored_claim.supporting_docs:
                parts.append("  Supporting evidence:")
                for doc in scored_claim.supporting_docs:
                    parts.append(f"    - {doc.title} [PMID:{doc.pmid}]")
            else:
                parts.append("  No supporting evidence found")
            
            if scored_claim.contradicting_docs:
                parts.append("  Contradicting evidence:")
                for doc in scored_claim.contradicting_docs:
                    parts.append(f"    - {doc.title} [PMID:{doc.pmid}]")
            
            parts.append("")
        
        parts.append("\nDOCUMENT ABSTRACTS (for context):\n")
        for doc in documents[:5]:  # Limit to top 5 for token efficiency
            parts.append(f"[PMID:{doc.pmid}] {doc.title}")
            abstract = doc.abstract[:300] + "..." if len(doc.abstract) > 300 else doc.abstract
            parts.append(f"Abstract: {abstract}\n")
        
        parts.append("\nIdentify what clinically important information is MISSING from this evidence.")
        
        return "\n".join(parts)


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def detect_gaps(
    scored_claims: list[ScoredClaim],
    documents: list[DocumentWithScore],
) -> tuple[list[GapResult], list[str]]:
    """
    Convenience function to detect evidence gaps.
    """
    detector = GapDetector()
    return await detector.detect(scored_claims, documents)
