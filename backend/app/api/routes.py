"""
API Routes — Thin HTTP layer over the services.

ENDPOINTS:
- POST /api/query            → Main endpoint: question → TrustReport
- POST /api/documents/ingest → Populate database from PubMed
- GET  /api/documents/{pmid} → Get single document details
- GET  /api/documents/count  → Check how many docs are embedded

The heavy lifting is done by services (especially QueryPipeline).
Routes handle HTTP concerns: validation, dependencies, responses.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import (
    QueryRequest,
    IngestRequest,
    TrustReport,
    DocumentResponse,
)

# Services
from app.services.pipeline import QueryPipeline
from app.services.pubmed import fetch_pubmed_articles
from app.services.embeddings import embed_all_documents
from app.services.document_service import DocumentService

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
    Ask a medical question, get a verified answer with trust metrics.
    
    The full pipeline:
    1. Expand query with medical synonyms
    2. Retrieve relevant documents (hybrid search)
    3. [Optional] Fetch from PubMed if coverage is low
    4. Generate answer with citations
    5. Run Trust Layer (verify, extract, score, confidence, gaps)
    6. Return TrustReport
    
    Example:
        POST /api/query
        {"question": "Do ACE inhibitors reduce mortality in heart failure?"}
        
    With live fetch:
        {"question": "...", "live_fetch": true, "max_fetch": 50}
    """
    pipeline = QueryPipeline(db)
    
    return await pipeline.run(
        question=request.question,
        top_k=request.top_k,
        live_fetch=request.live_fetch,
        max_fetch=request.max_fetch,
    )


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
    
    1. Searches PubMed for articles matching the search term
    2. Saves them to the database (skips duplicates)
    3. Generates embeddings for all new documents
    
    Example:
        POST /api/documents/ingest
        {"search_term": "ACE inhibitors heart failure", "max_results": 100}
        
        Returns {"fetched": 100, "saved": 85, "embedded": 85}
    """
    logger.info(f"Ingesting documents for: '{request.search_term}' (max {request.max_results})")
    
    # Fetch from PubMed
    articles = await fetch_pubmed_articles(request.search_term, request.max_results)
    logger.info(f"Fetched {len(articles)} articles from PubMed")
    
    if not articles:
        return {"fetched": 0, "saved": 0, "embedded": 0}
    
    # Save to database
    doc_service = DocumentService(db)
    saved_count = await doc_service.save_articles(articles)
    
    # Generate embeddings
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
    doc_service = DocumentService(db)
    return await doc_service.count()


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
    doc_service = DocumentService(db)
    doc = await doc_service.get_by_pmid(pmid)
    
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
