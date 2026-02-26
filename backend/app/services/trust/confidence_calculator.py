"""
Confidence Calculator Service.

WHAT THIS DOES:
Computes a confidence score (0-1) for each claim and the overall answer.
This is NOT the model's logprobs — it's based on evidence quality.

WHY THIS MATTERS:
Model confidence (logprobs) just tells you how certain the model is about its words.
Evidence confidence tells you how well-supported the claim actually is.

FORMULA:
confidence = evidence_agreement × log(num_sources + 1) × quality_weight

Where:
- evidence_agreement = (supporting - contradicting) / total docs
- num_sources = number of supporting documents (more = better)
- quality_weight = 1.0 for now (could weight RCT > observational later)

EXAMPLE:
    Claim: "ACE inhibitors reduce mortality"
    - 3 supporting docs
    - 0 contradicting docs
    - 1 neutral doc
    
    evidence_agreement = (3 - 0) / 4 = 0.75
    source_factor = log(3 + 1) / log(10 + 1) = 0.58  (normalized)
    confidence = 0.75 × 0.58 × 1.0 = 0.44
    
    Then scaled to 0-1 range.

USAGE:
    calculator = ConfidenceCalculator()
    claims_with_confidence = calculator.calculate(scored_claims)
"""

import math
import logging
from dataclasses import dataclass

from app.models.schemas import Claim, EvidenceSummary
from app.services.trust.attribution_scorer import ScoredClaim

logger = logging.getLogger(__name__)

# Maximum expected sources (for normalization)
MAX_EXPECTED_SOURCES = 10


@dataclass
class ConfidenceResult:
    """Result of confidence calculation for a single claim."""
    claim_id: str
    claim_text: str
    confidence: float
    evidence_agreement: float
    num_supporting: int
    num_contradicting: int
    num_neutral: int


class ConfidenceCalculator:
    """
    Calculates evidence-based confidence scores.
    
    This is NOT model confidence (logprobs).
    It's based on how well the evidence supports the claims.
    
    Pipeline position:
    Answer → ClaimExtractor → AttributionScorer → [ConfidenceCalculator] → ...
    """
    
    def calculate_claim_confidence(self, scored_claim: ScoredClaim) -> float:
        """
        Calculate confidence for a single claim.
        
        Formula:
        1. evidence_agreement = (supporting - contradicting) / total
        2. source_factor = log(supporting + 1) / log(MAX + 1)
        3. confidence = agreement × source_factor
        4. Clamp to [0, 1] and adjust for edge cases
        
        Returns:
            Confidence score between 0 and 1
        """
        num_supporting = len(scored_claim.supporting_docs)
        num_contradicting = len(scored_claim.contradicting_docs)
        num_neutral = len(scored_claim.neutral_docs)
        total = num_supporting + num_contradicting + num_neutral
        
        # Edge case: no evidence
        if total == 0:
            return 0.0
        
        # Evidence agreement: how much agreement vs disagreement
        # Range: -1 (all contradict) to +1 (all support)
        agreement = (num_supporting - num_contradicting) / total
        
        # Source factor: more sources = higher confidence (diminishing returns)
        # log(n+1) / log(max+1) gives us a 0-1 scale
        source_factor = math.log(num_supporting + 1) / math.log(MAX_EXPECTED_SOURCES + 1)
        source_factor = min(source_factor, 1.0)  # Cap at 1.0
        
        # Combine: agreement weighted by source factor
        # If agreement is negative (more contradictions), confidence should be low
        if agreement < 0:
            # Contradicting evidence = low confidence
            confidence = 0.1 + (agreement + 1) * 0.2  # Maps -1..0 to 0.1..0.3
        else:
            # Supporting evidence = higher confidence
            confidence = 0.3 + agreement * source_factor * 0.7  # Maps to 0.3..1.0
        
        return max(0.0, min(1.0, confidence))
    
    def calculate_all(
        self,
        scored_claims: list[ScoredClaim],
    ) -> tuple[list[ConfidenceResult], float, EvidenceSummary]:
        """
        Calculate confidence for all claims and compute overall confidence.
        
        Args:
            scored_claims: Claims with attribution scores
            
        Returns:
            Tuple of:
            - List of ConfidenceResult for each claim
            - Overall confidence score (0-1)
            - EvidenceSummary with aggregate stats
        """
        if not scored_claims:
            return [], 0.0, EvidenceSummary(
                total_sources=0,
                supporting=0,
                contradicting=0,
                neutral=0,
            )
        
        # Calculate confidence for each claim
        results = []
        total_supporting = 0
        total_contradicting = 0
        total_neutral = 0
        seen_pmids = set()
        
        for i, scored_claim in enumerate(scored_claims):
            confidence = self.calculate_claim_confidence(scored_claim)
            
            result = ConfidenceResult(
                claim_id=f"claim_{i + 1}",
                claim_text=scored_claim.claim.text,
                confidence=confidence,
                evidence_agreement=scored_claim.support_score,
                num_supporting=len(scored_claim.supporting_docs),
                num_contradicting=len(scored_claim.contradicting_docs),
                num_neutral=len(scored_claim.neutral_docs),
            )
            results.append(result)
            
            # Track unique documents for summary
            for doc in scored_claim.supporting_docs:
                if doc.pmid not in seen_pmids:
                    total_supporting += 1
                    seen_pmids.add(doc.pmid)
            for doc in scored_claim.contradicting_docs:
                if doc.pmid not in seen_pmids:
                    total_contradicting += 1
                    seen_pmids.add(doc.pmid)
            for doc in scored_claim.neutral_docs:
                if doc.pmid not in seen_pmids:
                    total_neutral += 1
                    seen_pmids.add(doc.pmid)
        
        # Overall confidence: weighted average of claim confidences
        # Weight by number of supporting docs (claims with more evidence matter more)
        total_weight = sum(r.num_supporting + 1 for r in results)
        overall_confidence = sum(
            r.confidence * (r.num_supporting + 1) 
            for r in results
        ) / total_weight if total_weight > 0 else 0.0
        
        # Build evidence summary
        summary = EvidenceSummary(
            total_sources=len(seen_pmids),
            supporting=total_supporting,
            contradicting=total_contradicting,
            neutral=total_neutral,
        )
        
        logger.info(
            f"Calculated confidence: overall={overall_confidence:.2f}, "
            f"claims={len(results)}, sources={len(seen_pmids)}"
        )
        
        return results, overall_confidence, summary


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def calculate_confidence(
    scored_claims: list[ScoredClaim],
) -> tuple[list[ConfidenceResult], float, EvidenceSummary]:
    """
    Convenience function to calculate confidence scores.
    """
    calculator = ConfidenceCalculator()
    return calculator.calculate_all(scored_claims)
