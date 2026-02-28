"""
Citation Verifier Service.

WHAT THIS DOES:
Detects hallucinated citations — PMIDs that appear in the generated answer
but were NOT in the retrieved documents.

WHY THIS MATTERS:
LLMs can "hallucinate" citations that look plausible but are either:
1. Completely made up (don't exist)
2. Real but not retrieved (from training data, not our evidence)

Both cases are problematic for a trustworthy medical system — the answer
claims evidence that isn't actually grounded in the retrieved documents.

EXAMPLE:
    Retrieved docs: [PMID:12345, PMID:67890]
    Answer: "ACE inhibitors reduce mortality [PMID:12345][PMID:99999]..."
    
    Hallucinated: ["99999"]  ← This PMID wasn't in our retrieved docs!

USAGE:
    verifier = CitationVerifier()
    result = verifier.verify(answer, retrieved_docs)
    
    if result.hallucinated_pmids:
        logger.warning(f"Found hallucinated citations: {result.hallucinated_pmids}")
"""

import re
import logging
from dataclasses import dataclass

from app.models.schemas import DocumentWithScore

logger = logging.getLogger(__name__)

# Regex pattern to extract PMIDs from answer text
# Matches [PMID:12345] format
PMID_PATTERN = r'\[PMID:(\d+)\]'


@dataclass
class VerificationResult:
    """Result of citation verification."""
    
    cited_pmids: list[str]
    """All PMIDs cited in the answer."""
    
    valid_pmids: list[str]
    """PMIDs that exist in the retrieved documents."""
    
    hallucinated_pmids: list[str]
    """PMIDs that do NOT exist in the retrieved documents."""
    
    @property
    def has_hallucinations(self) -> bool:
        """True if any hallucinated citations were found."""
        return len(self.hallucinated_pmids) > 0
    
    @property
    def hallucination_rate(self) -> float:
        """Fraction of citations that are hallucinated (0-1)."""
        if not self.cited_pmids:
            return 0.0
        return len(self.hallucinated_pmids) / len(self.cited_pmids)


class CitationVerifier:
    """
    Verifies that citations in the generated answer exist in retrieved documents.
    
    Pipeline position:
    Generator → Answer → [CitationVerifier] → Verification Result
                                ↓
                         ClaimExtractor → ...
    
    This runs BEFORE claim extraction to catch hallucinations early.
    """
    
    def verify(
        self,
        answer: str,
        retrieved_docs: list[DocumentWithScore],
    ) -> VerificationResult:
        """
        Verify all citations in the answer against retrieved documents.
        
        Args:
            answer: The generated answer text with [PMID:xxxxx] citations
            retrieved_docs: Documents that were retrieved for this query
            
        Returns:
            VerificationResult with valid and hallucinated PMIDs
            
        Example:
            verifier = CitationVerifier()
            result = verifier.verify(
                "ACE inhibitors work [PMID:12345][PMID:99999].",
                retrieved_docs  # Contains only PMID:12345
            )
            # result.hallucinated_pmids = ["99999"]
        """
        # Extract all PMIDs cited in the answer
        cited_pmids = self._extract_pmids(answer)
        
        # Get set of PMIDs that were actually retrieved
        retrieved_pmids = {doc.pmid for doc in retrieved_docs}
        
        # Separate valid from hallucinated
        valid_pmids = []
        hallucinated_pmids = []
        
        for pmid in cited_pmids:
            if pmid in retrieved_pmids:
                valid_pmids.append(pmid)
            else:
                hallucinated_pmids.append(pmid)
        
        # Log findings
        if hallucinated_pmids:
            logger.warning(
                f"Detected {len(hallucinated_pmids)} hallucinated citation(s): {hallucinated_pmids}"
            )
        else:
            logger.info(f"All {len(cited_pmids)} citations verified against retrieved documents")
        
        return VerificationResult(
            cited_pmids=cited_pmids,
            valid_pmids=valid_pmids,
            hallucinated_pmids=hallucinated_pmids,
        )
    
    def _extract_pmids(self, text: str) -> list[str]:
        """
        Extract all PMIDs from text.
        
        Finds all occurrences of [PMID:xxxxx] and returns the IDs.
        Preserves order, removes duplicates.
        """
        matches = re.findall(PMID_PATTERN, text)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_pmids = []
        for pmid in matches:
            if pmid not in seen:
                seen.add(pmid)
                unique_pmids.append(pmid)
        
        return unique_pmids


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def verify_citations(
    answer: str,
    retrieved_docs: list[DocumentWithScore],
) -> VerificationResult:
    """
    Convenience function to verify citations in an answer.
    
    Example:
        result = verify_citations(answer, documents)
        if result.has_hallucinations:
            print(f"Warning: {result.hallucinated_pmids}")
    """
    verifier = CitationVerifier()
    return verifier.verify(answer, retrieved_docs)
