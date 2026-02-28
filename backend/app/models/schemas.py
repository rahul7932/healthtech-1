"""
Pydantic schemas for API request/response validation.

These define the shape of data that goes in and out of the API.
The TrustReport is the core output of the entire system.

FLOW OVERVIEW:
==============
1. User sends QueryRequest to /api/query
2. System retrieves documents → DocumentWithScore[]
3. RAG generates answer with citations
4. Trust Layer produces TrustReport (claims, confidence, gaps)
5. Dashboard displays the TrustReport
"""

from datetime import date, datetime
from pydantic import BaseModel, Field


# =============================================================================
# DOCUMENT SCHEMAS (for PubMed abstracts)
# =============================================================================
#
# WHEN USED:
# - DocumentBase: Internal, shared fields for inheritance
# - DocumentResponse: GET /api/documents/{pmid} response
# - DocumentWithScore: Returned by retriever during vector search
#

class DocumentBase(BaseModel):
    """Fields common to all document representations."""
    pmid: str
    title: str
    abstract: str
    authors: list[str] | None = None
    publication_date: date | None = None
    journal: str | None = None


class DocumentResponse(DocumentBase):
    """
    Document as returned by the API.
    
    USED BY: GET /api/documents/{pmid}
    WHEN: User wants to see full details of a specific document
    """
    id: int
    created_at: datetime
    has_embedding: bool = Field(description="Whether this document has been embedded")
    
    class Config:
        from_attributes = True  # Allows creating from SQLAlchemy model


class DocumentWithScore(DocumentBase):
    """
    Document with a relevance score from vector search.
    
    USED BY: Retriever service (internal)
    WHEN: After vector similarity search, before passing to RAG generator
    """
    id: int
    relevance_score: float = Field(description="Cosine similarity score (0-1)")


# =============================================================================
# TRUST LAYER SCHEMAS (the core of the project)
# =============================================================================
#
# WHEN USED:
# - EvidenceReference: Created by AttributionScorer, links claims to sources
# - Claim: Created by ClaimExtractor, enriched by AttributionScorer + GapDetector
# - EvidenceSummary: Computed by ConfidenceCalculator, aggregate stats
# - TrustReport: Final output of /api/query, displayed in dashboard
#
# PIPELINE:
# ClaimExtractor → AttributionScorer → ConfidenceCalculator → GapDetector → TrustReport
#

class EvidenceReference(BaseModel):
    """
    A reference to a document that supports/contradicts a claim.
    
    USED BY: AttributionScorer service
    WHEN: After scoring each claim against retrieved documents
    DISPLAYED: In the EvidenceMap component (shows claim→source connections)
    """
    pmid: str
    title: str
    relevance_score: float = Field(
        description="How relevant this document is to the claim (0-1)"
    )


class Claim(BaseModel):
    """
    An atomic claim extracted from the generated answer.
    
    USED BY: Created by ClaimExtractor, enriched by subsequent services
    WHEN: After RAG generates an answer, we break it into verifiable pieces
    DISPLAYED: In AnswerPanel (highlighted text) and EvidenceMap (nodes)
    
    LIFECYCLE:
    1. ClaimExtractor creates Claim with text + spans
    2. AttributionScorer adds supporting/contradicting/neutral docs
    3. ConfidenceCalculator computes confidence score
    4. GapDetector adds missing_evidence list
    
    Example:
        Answer: "ACE inhibitors reduce mortality in heart failure patients."
        Claim 1: "ACE inhibitors reduce mortality"
        Claim 2: "This applies to heart failure patients"
    """
    id: str = Field(description="Unique identifier for this claim (e.g., 'claim_1')")
    text: str = Field(description="The claim text itself")
    
    # Where in the answer this claim appears (character positions)
    # Used by frontend to highlight claims in the answer text
    span_start: int = Field(description="Start character position in the answer")
    span_end: int = Field(description="End character position in the answer")
    
    # Evidence mapping - populated by AttributionScorer
    supporting_docs: list[EvidenceReference] = Field(
        default_factory=list,
        description="Documents that support this claim"
    )
    contradicting_docs: list[EvidenceReference] = Field(
        default_factory=list,
        description="Documents that contradict this claim"
    )
    neutral_docs: list[EvidenceReference] = Field(
        default_factory=list,
        description="Documents that mention but don't clearly support/contradict"
    )
    
    # Confidence - computed by ConfidenceCalculator
    confidence: float = Field(
        ge=0, le=1,
        description="Confidence score for this claim (0-1)"
    )
    
    # Gaps - populated by GapDetector
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="What evidence is missing to fully verify this claim"
    )


class EvidenceSummary(BaseModel):
    """
    Aggregate statistics about the evidence used.
    
    USED BY: ConfidenceCalculator service
    WHEN: After all claims are scored, we compute totals
    DISPLAYED: In ConfidenceMeter component (pie chart or bar)
    """
    total_sources: int
    supporting: int
    contradicting: int
    neutral: int


class TrustReport(BaseModel):
    """
    The main output of the Trust Layer.
    
    USED BY: POST /api/query endpoint
    WHEN: After entire pipeline completes (retrieve → generate → verify)
    DISPLAYED: Entire dashboard renders from this single object
    
    This is what makes this project special - not just an answer,
    but a full epistemology report showing:
    - What claims were made
    - What evidence supports each claim
    - How confident we should be
    - What's missing
    
    FRONTEND MAPPING:
    - query → shown in QueryInput (what was asked)
    - answer → AnswerPanel (with claims highlighted)
    - claims → EvidenceMap (visual graph of claim→source)
    - overall_confidence → ConfidenceMeter (gauge visualization)
    - evidence_summary → ConfidenceMeter (breakdown pie/bar)
    - global_gaps → GapsPanel (list of uncertainties)
    """
    # The original question
    query: str
    
    # The generated answer (with inline citations like [PMID:12345])
    answer: str
    
    # Breakdown of the answer into verifiable claims
    claims: list[Claim] = Field(
        description="Atomic claims extracted from the answer, each with evidence mapping"
    )
    
    # Overall metrics
    overall_confidence: float = Field(
        ge=0, le=1,
        description="Aggregated confidence across all claims"
    )
    evidence_summary: EvidenceSummary
    
    # System-wide gaps (not tied to a specific claim)
    global_gaps: list[str] = Field(
        default_factory=list,
        description="Evidence gaps that affect the answer as a whole"
    )
    
    # Hallucinated citations (PMIDs cited but not in retrieved docs)
    hallucinated_citations: list[str] = Field(
        default_factory=list,
        description="PMIDs cited in the answer that were not in the retrieved documents"
    )


# =============================================================================
# API REQUEST SCHEMAS
# =============================================================================
#
# WHEN USED:
# - QueryRequest: User asks a medical question → triggers full pipeline
# - IngestRequest: Admin populates database with PubMed abstracts
#

class QueryRequest(BaseModel):
    """
    Request body for the /api/query endpoint.
    
    USED BY: POST /api/query
    WHEN: User submits a medical question from the dashboard
    TRIGGERS: Retrieve → Generate → Trust Layer → TrustReport
    
    Example:
        POST /api/query
        {"question": "Do ACE inhibitors reduce mortality in heart failure?"}
    """
    question: str = Field(
        min_length=10,
        description="The medical question to answer"
    )
    top_k: int = Field(
        default=10,
        ge=1, le=50,
        description="Number of documents to retrieve"
    )


class IngestRequest(BaseModel):
    """
    Request body for the /api/documents/ingest endpoint.
    
    USED BY: POST /api/documents/ingest
    WHEN: Populating the database with PubMed abstracts (run before querying)
    TRIGGERS: PubMed fetch → Embedding → Store in pgvector
    
    Example:
        POST /api/documents/ingest
        {"search_term": "ACE inhibitors heart failure", "max_results": 100}
    """
    search_term: str = Field(
        min_length=3,
        description="PubMed search term (e.g., 'ACE inhibitors heart failure')"
    )
    max_results: int = Field(
        default=100,
        ge=10, le=500,
        description="Maximum number of abstracts to fetch"
    )
