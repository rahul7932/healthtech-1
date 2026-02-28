"""
Coverage Checker Service.

WHAT THIS DOES:
Evaluates whether retrieved documents provide sufficient coverage for a query.
Used to decide if we need to fetch more documents from PubMed.

WHY THIS MATTERS:
When a user asks about a topic not well-represented in our database,
we want to detect this and optionally fetch relevant documents on-demand.

METRICS:
- Number of documents found
- Average relevance score of top results
- Minimum relevance threshold

USAGE:
    checker = CoverageChecker()
    result = checker.check(documents)
    
    if not result.is_sufficient:
        # Fetch more documents from PubMed
        ...
"""

import logging
from dataclasses import dataclass

from app.config import get_settings
from app.models.schemas import DocumentWithScore

logger = logging.getLogger(__name__)


@dataclass
class CoverageResult:
    """Result of coverage check."""
    
    is_sufficient: bool
    """Whether we have enough relevant documents."""
    
    document_count: int
    """Number of documents found."""
    
    avg_relevance: float
    """Average relevance score of top documents."""
    
    reason: str
    """Human-readable explanation of the result."""


class CoverageChecker:
    """
    Checks if retrieved documents provide sufficient coverage for answering a query.
    
    Coverage is considered insufficient if:
    - Too few documents are found (< min_documents)
    - Average relevance of top docs is below threshold
    """
    
    def __init__(
        self,
        threshold: float | None = None,
        min_documents: int = 3,
        top_n_for_avg: int = 5,
    ):
        """
        Initialize the coverage checker.
        
        Args:
            threshold: Minimum average relevance score (0-1). Defaults to config value.
            min_documents: Minimum number of documents required.
            top_n_for_avg: Number of top documents to use for average calculation.
        """
        settings = get_settings()
        self.threshold = threshold if threshold is not None else settings.coverage_threshold
        self.min_documents = min_documents
        self.top_n_for_avg = top_n_for_avg
    
    def check(self, documents: list[DocumentWithScore]) -> CoverageResult:
        """
        Check if documents provide sufficient coverage.
        
        Args:
            documents: Retrieved documents with relevance scores
            
        Returns:
            CoverageResult with is_sufficient flag and explanation
            
        Example:
            checker = CoverageChecker()
            result = checker.check(retrieved_docs)
            
            if not result.is_sufficient:
                print(f"Low coverage: {result.reason}")
                # Trigger PubMed fetch
        """
        doc_count = len(documents)
        
        # Check minimum document count
        if doc_count < self.min_documents:
            return CoverageResult(
                is_sufficient=False,
                document_count=doc_count,
                avg_relevance=0.0,
                reason=f"Only {doc_count} documents found (minimum: {self.min_documents})"
            )
        
        # Calculate average relevance of top N documents
        top_docs = documents[:self.top_n_for_avg]
        avg_relevance = sum(d.relevance_score for d in top_docs) / len(top_docs)
        
        # Check relevance threshold
        if avg_relevance < self.threshold:
            return CoverageResult(
                is_sufficient=False,
                document_count=doc_count,
                avg_relevance=avg_relevance,
                reason=f"Low relevance ({avg_relevance:.2f} < {self.threshold} threshold)"
            )
        
        # Coverage is sufficient
        return CoverageResult(
            is_sufficient=True,
            document_count=doc_count,
            avg_relevance=avg_relevance,
            reason=f"Good coverage: {doc_count} docs, {avg_relevance:.2f} avg relevance"
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def check_coverage(documents: list[DocumentWithScore]) -> CoverageResult:
    """
    Convenience function to check document coverage.
    
    Example:
        result = check_coverage(retrieved_docs)
        if not result.is_sufficient:
            # Fetch more from PubMed
    """
    checker = CoverageChecker()
    return checker.check(documents)
