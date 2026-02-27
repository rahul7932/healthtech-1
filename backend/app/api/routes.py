"""
API Routes — The endpoints that tie everything together.

ENDPOINTS:
- POST /api/query         → Main endpoint: question → TrustReport
- POST /api/documents/ingest → Populate database from PubMed
- GET  /api/documents/{pmid} → Get single document details
- GET  /api/documents/count  → Check how many docs are embedded

FLOW:
1. First, call /api/documents/ingest to populate the database
2. Then, call /api/query with your medical question
3. Get back a TrustReport with answer, claims, confidence, and gaps
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document
from app.models.schemas import (
    QueryRequest,
    IngestRequest,
    TrustReport,
    Claim,
    EvidenceReference,
    DocumentResponse,
)

# Services
from app.services.pubmed import fetch_pubmed_articles
from app.services.embeddings import embed_all_documents
from app.services.retriever import retrieve_documents
from app.services.generator import generate_answer
from app.services.trust.claim_extractor import extract_claims
from app.services.trust.attribution_scorer import score_claims
from app.services.trust.confidence_calculator import calculate_confidence
from app.services.trust.gap_detector import detect_gaps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


# =============================================================================
# MAIN QUERY ENDPOINT
# =============================================================================

@router.post("/query", response_model=TrustReport)
async def query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
) -> TrustReport:
    """
    The main endpoint — ask a medical question, get a verified answer.
    
    This runs the full pipeline:
    1. Retrieve relevant documents (pgvector similarity search)
    2. Generate answer with citations (GPT-4o)
    3. Extract claims from answer
    4. Score each claim against evidence
    5. Calculate confidence
    6. Detect evidence gaps
    7. Return TrustReport
    
    Example:
        POST /api/query
        {"question": "Do ACE inhibitors reduce mortality in heart failure?"}
        
        Returns TrustReport with answer, claims, confidence, gaps
    """
    question = request.question
    top_k = request.top_k
    
    logger.info(f"Processing query: '{question}'")
    
    # Step 1: Retrieve relevant documents
    documents = await retrieve_documents(question, db, top_k)
    
    if not documents:
        # No documents found — can't generate a proper answer
        return TrustReport(
            query=question,
            answer="I cannot answer this question because no relevant documents were found in the database. Please ingest relevant medical literature first.",
            claims=[],
            overall_confidence=0.0,
            evidence_summary={
                "total_sources": 0,
                "supporting": 0,
                "contradicting": 0,
                "neutral": 0,
            },
            global_gaps=["No relevant documents in database"],
        )
    
    logger.info(f"Retrieved {len(documents)} documents")
    
    # Step 2: Generate answer with citations
    answer = await generate_answer(question, documents)
    logger.info(f"Generated answer: {len(answer)} chars")
    
    # Step 3: Extract claims from the answer
    extracted_claims = await extract_claims(answer)
    logger.info(f"Extracted {len(extracted_claims)} claims")
    
    # Step 4: Score claims against evidence
    scored_claims = await score_claims(extracted_claims, documents)
    logger.info(f"Scored {len(scored_claims)} claims")
    
    # Step 5: Calculate confidence
    confidence_results, overall_confidence, evidence_summary = calculate_confidence(scored_claims)
    logger.info(f"Overall confidence: {overall_confidence:.2f}")
    
    # Step 6: Detect evidence gaps
    gap_results, global_gaps = await detect_gaps(scored_claims, documents)
    logger.info(f"Detected {len(global_gaps)} global gaps")
    
    # Step 7: Build the TrustReport
    claims = []
    for i, (scored_claim, conf_result, gap_result) in enumerate(
        zip(scored_claims, confidence_results, gap_results)
    ):
        claim = Claim(
            id=f"claim_{i + 1}",
            text=scored_claim.claim.text,
            span_start=scored_claim.claim.span_start,
            span_end=scored_claim.claim.span_end,
            supporting_docs=[
                EvidenceReference(
                    pmid=doc.pmid,
                    title=doc.title,
                    relevance_score=doc.relevance_score,
                )
                for doc in scored_claim.supporting_docs
            ],
            contradicting_docs=[
                EvidenceReference(
                    pmid=doc.pmid,
                    title=doc.title,
                    relevance_score=doc.relevance_score,
                )
                for doc in scored_claim.contradicting_docs
            ],
            neutral_docs=[
                EvidenceReference(
                    pmid=doc.pmid,
                    title=doc.title,
                    relevance_score=doc.relevance_score,
                )
                for doc in scored_claim.neutral_docs
            ],
            confidence=conf_result.confidence,
            missing_evidence=gap_result.gaps,
        )
        claims.append(claim)
    
    trust_report = TrustReport(
        query=question,
        answer=answer,
        claims=claims,
        overall_confidence=overall_confidence,
        evidence_summary=evidence_summary,
        global_gaps=global_gaps,
    )
    
    logger.info("TrustReport generated successfully")
    return trust_report


# =============================================================================
# DOCUMENT INGESTION
# =============================================================================

@router.post("/documents/ingest")
async def ingest_documents(
    request: IngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ingest documents from PubMed into the database.
    
    This endpoint:
    1. Searches PubMed for articles matching the search term
    2. Saves them to the database
    3. Generates embeddings for all new documents
    
    Run this BEFORE querying to populate the database.
    
    Example:
        POST /api/documents/ingest
        {"search_term": "ACE inhibitors heart failure", "max_results": 100}
        
        Returns {"fetched": 100, "saved": 85, "embedded": 85}
    """
    search_term = request.search_term
    max_results = request.max_results
    
    logger.info(f"Ingesting documents for: '{search_term}' (max {max_results})")
    
    # Step 1: Fetch from PubMed
    articles = await fetch_pubmed_articles(search_term, max_results)
    logger.info(f"Fetched {len(articles)} articles from PubMed")
    
    if not articles:
        return {"fetched": 0, "saved": 0, "embedded": 0}
    
    # Step 2: Save to database (skip duplicates)
    saved_count = 0
    for article in articles:
        # Check if already exists
        existing = await db.execute(
            select(Document).where(Document.pmid == article["pmid"])
        )
        if existing.scalar_one_or_none():
            continue
        
        # Create new document
        doc = Document(
            pmid=article["pmid"],
            title=article["title"],
            abstract=article["abstract"],
            authors=article.get("authors"),
            publication_date=article.get("publication_date"),
            journal=article.get("journal"),
        )
        db.add(doc)
        saved_count += 1
    
    await db.commit()
    logger.info(f"Saved {saved_count} new documents")
    
    # Step 3: Generate embeddings for all unembedded documents
    embedded_count = await embed_all_documents(db)
    logger.info(f"Embedded {embedded_count} documents")
    
    return {
        "fetched": len(articles),
        "saved": saved_count,
        "embedded": embedded_count,
    }


# =============================================================================
# DOCUMENT RETRIEVAL
# =============================================================================

# NOTE: /documents/count must come BEFORE /documents/{pmid} 
# otherwise FastAPI matches "count" as a pmid

@router.get("/documents/count")
async def count_documents(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get document counts — useful to check if database is ready.
    
    Example:
        GET /api/documents/count
        Returns {"total": 100, "embedded": 95, "pending": 5}
    """
    # Total documents
    total_result = await db.execute(select(func.count(Document.id)))
    total = total_result.scalar()
    
    # Documents with embeddings
    embedded_result = await db.execute(
        select(func.count(Document.id)).where(Document.embedding.isnot(None))
    )
    embedded = embedded_result.scalar()
    
    return {
        "total": total,
        "embedded": embedded,
        "pending": total - embedded,
    }


@router.get("/documents/{pmid}", response_model=DocumentResponse)
async def get_document(
    pmid: str,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Get a single document by its PubMed ID.
    
    Example:
        GET /api/documents/12345678
    """
    result = await db.execute(
        select(Document).where(Document.pmid == pmid)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {pmid} not found")
    
    return DocumentResponse(
        id=doc.id,
        pmid=doc.pmid,
        title=doc.title,
        abstract=doc.abstract,
        authors=doc.authors or [],
        publication_date=doc.publication_date,
        journal=doc.journal,
        created_at=doc.created_at,
        has_embedding=doc.embedding is not None,
    )
