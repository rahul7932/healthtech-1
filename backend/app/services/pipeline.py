"""
Query Pipeline — Orchestrates the full RAG + Trust Layer flow.

WHAT THIS DOES:
Coordinates all services to turn a medical question into a verified TrustReport.
This is the "brain" that ties retrieval, generation, and verification together.

WHY THIS EXISTS:
- Keeps API routes thin and focused on HTTP concerns
- Makes the pipeline testable in isolation
- Single place to understand the full flow
- Easy to extend or modify pipeline steps

PIPELINE STAGES:
1. Retrieval: Expand query → Retrieve docs → (optional) Live fetch from PubMed
2. Generation: Generate answer with citations (standard or agentic debate)
3. Trust Layer: Verify citations → Extract claims → Score → Confidence → Gaps
4. Assembly: Build the TrustReport

GENERATION MODES:
- Standard: Single-pass GPT-4o generation (default)
- Agentic Debate: Multiple advocates argue for documents, synthesizer combines
  Enable via USE_AGENTIC_DEBATE=true in config

USAGE:
    pipeline = QueryPipeline(db)
    report = await pipeline.run(
        question="Do ACE inhibitors reduce mortality?",
        top_k=10,
        live_fetch=True,
        max_fetch=50,
    )
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.schemas import (
    TrustReport,
    Claim,
    EvidenceReference,
    EvidenceSummary,
    DocumentWithScore,
)

# Services
from app.services.query_expander import expand_query
from app.services.retriever import retrieve_documents
from app.services.coverage_checker import check_coverage
from app.services.pubmed_query_generator import generate_pubmed_query
from app.services.pubmed import fetch_pubmed_articles
from app.services.embeddings import embed_all_documents
from app.services.generator import generate_answer
from app.services.document_service import DocumentService
from app.services.trust.citation_verifier import verify_citations, VerificationResult
from app.services.trust.claim_extractor import extract_claims, ExtractedClaim
from app.services.trust.attribution_scorer import score_claims, ScoredClaim
from app.services.trust.confidence_calculator import calculate_confidence
from app.services.trust.gap_detector import detect_gaps

# Agentic Debate (lazy import to avoid circular dependencies)
from app.services.debate import run_debate, DebateResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Intermediate result tracking through the pipeline."""
    
    # Input
    question: str
    top_k: int
    live_fetch: bool
    max_fetch: int
    
    # Retrieval stage
    expanded_query: str = ""
    documents: list[DocumentWithScore] = None
    fetch_triggered: bool = False
    documents_fetched: int = 0
    
    # Generation stage
    answer: str = ""
    debate_result: Optional[DebateResult] = None  # Only set if debate mode is used
    
    # Trust layer stage
    citation_result: VerificationResult = None
    extracted_claims: list[ExtractedClaim] = None
    scored_claims: list[ScoredClaim] = None
    confidence_results: list = None
    overall_confidence: float = 0.0
    evidence_summary: EvidenceSummary = None
    gap_results: list = None
    global_gaps: list[str] = None
    
    def __post_init__(self):
        if self.documents is None:
            self.documents = []
        if self.global_gaps is None:
            self.global_gaps = []


class QueryPipeline:
    """
    Orchestrates the full query pipeline from question to TrustReport.
    
    This class coordinates all the services needed to:
    1. Find relevant documents
    2. Generate a cited answer
    3. Verify and score the answer
    4. Produce a trust report
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the pipeline with a database session.
        
        Args:
            db: SQLAlchemy async session for database operations
        """
        self.db = db
    
    async def run(
        self,
        question: str,
        top_k: int = 10,
        live_fetch: bool = False,
        max_fetch: int = 50,
    ) -> TrustReport:
        """
        Run the full pipeline and return a TrustReport.
        
        Args:
            question: The medical question to answer
            top_k: Number of documents to retrieve
            live_fetch: Whether to fetch from PubMed if coverage is low
            max_fetch: Max documents to fetch from PubMed
            
        Returns:
            TrustReport with answer, claims, confidence, and gaps
        """
        logger.info(f"Pipeline starting: '{question}' (live_fetch={live_fetch})")
        
        # Initialize result tracking
        result = PipelineResult(
            question=question,
            top_k=top_k,
            live_fetch=live_fetch,
            max_fetch=max_fetch,
        )
        
        # Stage 1: Retrieval
        await self._stage_retrieval(result)
        
        # Early exit if no documents
        if not result.documents:
            return self._build_empty_report(result)
        
        # Stage 2: Generation
        await self._stage_generation(result)
        
        # Stage 3: Trust Layer
        await self._stage_trust_layer(result)
        
        # Stage 4: Build final report
        report = self._build_trust_report(result)
        
        logger.info(
            f"Pipeline complete: confidence={result.overall_confidence:.2f}, "
            f"claims={len(result.scored_claims)}, fetch_triggered={result.fetch_triggered}"
        )
        
        return report
    
    # =========================================================================
    # STAGE 1: RETRIEVAL
    # =========================================================================
    
    async def _stage_retrieval(self, result: PipelineResult) -> None:
        """
        Retrieve relevant documents, optionally fetching from PubMed.
        
        Steps:
        1. Expand query with medical synonyms
        2. Retrieve from database
        3. If live_fetch and low coverage, fetch from PubMed
        4. Re-retrieve if new docs were added
        """
        # Expand query
        result.expanded_query = await expand_query(result.question)
        logger.info(f"Expanded query: '{result.expanded_query[:80]}...'")
        
        # Initial retrieval
        result.documents = await retrieve_documents(
            result.expanded_query, self.db, result.top_k
        )
        
        # Check coverage and optionally fetch more
        if result.live_fetch:
            await self._handle_live_fetch(result)
        
        logger.info(f"Retrieval complete: {len(result.documents)} documents")
    
    async def _handle_live_fetch(self, result: PipelineResult) -> None:
        """Handle live fetching from PubMed if coverage is insufficient."""
        coverage = check_coverage(result.documents)
        logger.info(f"Coverage check: {coverage.reason}")
        
        if coverage.is_sufficient:
            return
        
        logger.info("Low coverage detected, fetching from PubMed...")
        result.fetch_triggered = True
        
        # Generate optimized PubMed search query
        pubmed_query = await generate_pubmed_query(result.question)
        logger.info(f"PubMed search query: '{pubmed_query}'")
        
        # Fetch and save articles
        articles = await fetch_pubmed_articles(pubmed_query, result.max_fetch)
        logger.info(f"Fetched {len(articles)} articles from PubMed")
        
        if articles:
            result.documents_fetched = await self._save_articles(articles)
            
            # Embed new documents
            if result.documents_fetched > 0:
                embedded = await embed_all_documents(self.db)
                logger.info(f"Embedded {embedded} new documents")
            
            # Re-retrieve with new documents
            result.documents = await retrieve_documents(
                result.expanded_query, self.db, result.top_k
            )
            logger.info(f"Re-retrieved {len(result.documents)} documents after fetch")
    
    async def _save_articles(self, articles: list[dict]) -> int:
        """Save articles to database, skipping duplicates. Returns count saved."""
        doc_service = DocumentService(self.db)
        return await doc_service.save_articles(articles)
    
    # =========================================================================
    # STAGE 2: GENERATION
    # =========================================================================
    
    async def _stage_generation(self, result: PipelineResult) -> None:
        """
        Generate an answer with citations.
        
        Uses either standard generation or agentic debate based on config.
        The debate system runs multiple advocates then synthesizes their arguments.
        """
        settings = get_settings()
        
        if settings.use_agentic_debate:
            # Agentic debate: multiple advocates argue, synthesizer combines
            logger.info(
                f"Using agentic debate with {settings.debate_num_advocates} advocates"
            )
            debate_result = await run_debate(
                query=result.question,
                documents=result.documents,
                num_advocates=settings.debate_num_advocates,
            )
            result.answer = debate_result.answer
            result.debate_result = debate_result
            logger.info(
                f"Debate complete: {debate_result.num_advocates} advocates, "
                f"avg confidence {debate_result.average_confidence:.2f}, "
                f"answer {len(result.answer)} chars"
            )
        else:
            # Standard single-pass generation
            result.answer = await generate_answer(result.question, result.documents)
            logger.info(f"Generated answer: {len(result.answer)} chars")
    
    # =========================================================================
    # STAGE 3: TRUST LAYER
    # =========================================================================
    
    async def _stage_trust_layer(self, result: PipelineResult) -> None:
        """
        Run the full trust layer pipeline.
        
        Steps:
        1. Verify citations (detect hallucinations)
        2. Extract claims
        3. Score claims against evidence
        4. Calculate confidence
        5. Detect evidence gaps
        6. Apply hallucination penalties
        """
        # Verify citations
        result.citation_result = verify_citations(result.answer, result.documents)
        if result.citation_result.has_hallucinations:
            logger.warning(
                f"Hallucinated citations: {result.citation_result.hallucinated_pmids}"
            )
        
        # Extract claims
        result.extracted_claims = await extract_claims(result.answer)
        logger.info(f"Extracted {len(result.extracted_claims)} claims")
        
        # Score claims
        result.scored_claims = await score_claims(
            result.extracted_claims, result.documents
        )
        logger.info(f"Scored {len(result.scored_claims)} claims")
        
        # Calculate confidence
        (
            result.confidence_results,
            result.overall_confidence,
            result.evidence_summary,
        ) = calculate_confidence(result.scored_claims)
        logger.info(f"Overall confidence: {result.overall_confidence:.2f}")
        
        # Detect gaps
        result.gap_results, result.global_gaps = await detect_gaps(
            result.scored_claims, result.documents
        )
        logger.info(f"Detected {len(result.global_gaps)} global gaps")
        
        # Apply hallucination penalties
        self._apply_hallucination_penalties(result)
    
    def _apply_hallucination_penalties(self, result: PipelineResult) -> None:
        """Apply confidence penalty and add warnings for hallucinated citations."""
        if not result.citation_result.has_hallucinations:
            return
        
        # Reduce confidence
        penalty = result.citation_result.hallucination_rate
        original = result.overall_confidence
        result.overall_confidence = original * (1 - penalty)
        logger.info(
            f"Applied hallucination penalty: {original:.2f} → {result.overall_confidence:.2f} "
            f"({penalty:.0%} of citations unverified)"
        )
        
        # Add warning to global gaps
        count = len(result.citation_result.hallucinated_pmids)
        pmids_str = ", ".join(result.citation_result.hallucinated_pmids[:3])
        if count > 3:
            pmids_str += f", ... (+{count - 3} more)"
        result.global_gaps.insert(
            0, f"Warning: {count} citation(s) could not be verified (PMIDs: {pmids_str})"
        )
    
    # =========================================================================
    # STAGE 4: BUILD REPORT
    # =========================================================================
    
    def _build_trust_report(self, result: PipelineResult) -> TrustReport:
        """Assemble the final TrustReport from pipeline results."""
        claims = self._build_claims(result)
        
        return TrustReport(
            query=result.question,
            answer=result.answer,
            claims=claims,
            overall_confidence=result.overall_confidence,
            evidence_summary=result.evidence_summary,
            global_gaps=result.global_gaps,
            hallucinated_citations=result.citation_result.hallucinated_pmids,
            fetch_triggered=result.fetch_triggered,
            documents_fetched=result.documents_fetched,
        )
    
    def _build_claims(self, result: PipelineResult) -> list[Claim]:
        """Build Claim objects from scored claims and other results."""
        claims = []
        
        for i, (scored_claim, conf_result, gap_result) in enumerate(
            zip(result.scored_claims, result.confidence_results, result.gap_results)
        ):
            claim = Claim(
                id=f"claim_{i + 1}",
                text=scored_claim.claim.text,
                span_start=scored_claim.claim.span_start,
                span_end=scored_claim.claim.span_end,
                supporting_docs=self._build_evidence_refs(scored_claim.supporting_docs),
                contradicting_docs=self._build_evidence_refs(scored_claim.contradicting_docs),
                neutral_docs=self._build_evidence_refs(scored_claim.neutral_docs),
                confidence=conf_result.confidence,
                missing_evidence=gap_result.gaps,
            )
            claims.append(claim)
        
        return claims
    
    def _build_evidence_refs(self, docs: list) -> list[EvidenceReference]:
        """Convert document objects to EvidenceReference schema objects."""
        return [
            EvidenceReference(
                pmid=doc.pmid,
                title=doc.title,
                relevance_score=doc.relevance_score,
            )
            for doc in docs
        ]
    
    def _build_empty_report(self, result: PipelineResult) -> TrustReport:
        """Build a TrustReport when no documents were found."""
        return TrustReport(
            query=result.question,
            answer=(
                "I cannot answer this question because no relevant documents "
                "were found in the database. Try enabling live_fetch to "
                "retrieve documents from PubMed."
            ),
            claims=[],
            overall_confidence=0.0,
            evidence_summary=EvidenceSummary(
                total_sources=0,
                supporting=0,
                contradicting=0,
                neutral=0,
            ),
            global_gaps=["No relevant documents in database"],
            hallucinated_citations=[],
            fetch_triggered=result.fetch_triggered,
            documents_fetched=result.documents_fetched,
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def run_query_pipeline(
    question: str,
    db: AsyncSession,
    top_k: int = 10,
    live_fetch: bool = False,
    max_fetch: int = 50,
) -> TrustReport:
    """
    Convenience function to run the query pipeline.
    
    Example:
        report = await run_query_pipeline(
            "Do ACE inhibitors reduce mortality?",
            db,
            live_fetch=True,
        )
    """
    pipeline = QueryPipeline(db)
    return await pipeline.run(
        question=question,
        top_k=top_k,
        live_fetch=live_fetch,
        max_fetch=max_fetch,
    )
