"""
Document Retriever Service.

WHAT THIS DOES:
Finds the most relevant documents using HYBRID SEARCH:
- Semantic search (pgvector cosine similarity)
- Keyword search (PostgreSQL full-text search)

WHY HYBRID?
- Semantic search understands meaning but can miss exact terms
- Keyword search catches exact matches but misses synonyms
- Combined, they cover both cases

HOW IT WORKS:
1. User asks: "Do ACE inhibitors reduce mortality?"
2. We embed the query → 1536-dim vector
3. Run BOTH searches:
   - pgvector: semantic similarity (cosine distance)
   - ts_rank: keyword match score
4. Combine scores: alpha * semantic + (1-alpha) * keyword
5. Return top-K by combined score

SCORE COMBINATION:
- alpha = 1.0 → pure semantic search
- alpha = 0.0 → pure keyword search
- alpha = 0.7 → 70% semantic, 30% keyword (default)

pgvector OPERATORS:
- <-> : L2 distance (Euclidean)
- <#> : Inner product (negative, for max inner product search)  
- <=> : Cosine distance (what we use - best for text similarity)

USAGE:
    retriever = Retriever()
    
    # Hybrid search (default)
    results = await retriever.search("ACE inhibitors heart failure", db, top_k=10)
    
    # Pure semantic search
    results = await retriever.search_semantic("ACE inhibitors", db, top_k=10)
    
    # Pure keyword search
    results = await retriever.search_keyword("ACE inhibitors", db, top_k=10)
"""

import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import Document
from app.models.schemas import DocumentWithScore
from app.services.embeddings import embed_query

logger = logging.getLogger(__name__)


class Retriever:
    """
    Retrieves relevant documents using HYBRID SEARCH.
    
    Combines semantic (vector) and keyword (full-text) search for
    better retrieval than either alone.
    """
    
    def __init__(self):
        settings = get_settings()
        self.alpha = settings.hybrid_search_alpha
    
    # =========================================================================
    # MAIN SEARCH METHOD (HYBRID)
    # =========================================================================
    
    async def search(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[DocumentWithScore]:
        """
        Hybrid search combining semantic and keyword matching.
        
        This is the main method you'll use. It:
        1. Embeds the query using OpenAI
        2. Runs BOTH semantic and keyword search in one query
        3. Combines scores: alpha * semantic + (1-alpha) * keyword
        4. Returns top-K by combined score
        
        Args:
            query: The search query (e.g., "Do ACE inhibitors reduce mortality?")
            db: Database session
            top_k: Number of results to return (default: 10)
            
        Returns:
            List of DocumentWithScore, ordered by combined relevance
        """
        logger.info(f"Hybrid search for: '{query}' (top_k={top_k}, alpha={self.alpha})")
        
        # Embed the query for semantic search
        query_vector = await embed_query(query)
        
        # Run hybrid search
        return await self._search_hybrid(query, query_vector, db, top_k)
    
    async def _search_hybrid(
        self,
        query_text: str,
        query_vector: list[float],
        db: AsyncSession,
        top_k: int,
    ) -> list[DocumentWithScore]:
        """
        Execute hybrid search combining semantic and keyword scores.
        
        The SQL query:
        1. Computes semantic_score from pgvector cosine similarity
        2. Computes keyword_score from ts_rank (normalized to 0-1)
        3. Combines: alpha * semantic + (1-alpha) * keyword
        4. Orders by combined score
        """
        # Convert query to tsquery format for full-text search
        # plainto_tsquery handles natural language queries
        stmt = text("""
            WITH scores AS (
                SELECT 
                    id, pmid, title, abstract, authors, publication_date, journal,
                    -- Semantic score: cosine similarity (0 to 1)
                    1 - (embedding <=> :query_vector) AS semantic_score,
                    -- Keyword score: ts_rank normalized (0 to 1)
                    -- ts_rank returns ~0-1 but can exceed 1, so we cap it
                    LEAST(ts_rank(search_vector, plainto_tsquery('english', :query_text)), 1.0) AS keyword_score
                FROM documents
                WHERE embedding IS NOT NULL
                  AND search_vector IS NOT NULL
            )
            SELECT 
                id, pmid, title, abstract, authors, publication_date, journal,
                semantic_score,
                keyword_score,
                -- Combined score: weighted average
                (:alpha * semantic_score + (1 - :alpha) * COALESCE(keyword_score, 0)) AS relevance_score
            FROM scores
            ORDER BY relevance_score DESC
            LIMIT :top_k
        """)
        
        result = await db.execute(
            stmt,
            {
                "query_vector": str(query_vector),
                "query_text": query_text,
                "alpha": self.alpha,
                "top_k": top_k,
            }
        )
        rows = result.fetchall()
        
        # Convert to DocumentWithScore objects
        documents = []
        for row in rows:
            doc = DocumentWithScore(
                id=row.id,
                pmid=row.pmid,
                title=row.title,
                abstract=row.abstract,
                authors=row.authors or [],
                publication_date=row.publication_date,
                journal=row.journal,
                relevance_score=float(row.relevance_score),
            )
            documents.append(doc)
            
            # Log individual scores for debugging
            logger.debug(
                f"  {row.pmid}: semantic={row.semantic_score:.3f}, "
                f"keyword={row.keyword_score:.3f}, combined={row.relevance_score:.3f}"
            )
        
        logger.info(f"Found {len(documents)} documents via hybrid search")
        return documents
    
    # =========================================================================
    # INDIVIDUAL SEARCH METHODS (for testing/comparison)
    # =========================================================================
    
    async def search_semantic(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[DocumentWithScore]:
        """
        Pure semantic search using only vector similarity.
        
        Use this to compare with hybrid search or when you only
        want embedding-based results.
        """
        logger.info(f"Semantic search for: '{query}' (top_k={top_k})")
        
        query_vector = await embed_query(query)
        
        stmt = text("""
            SELECT 
                id, pmid, title, abstract, authors, publication_date, journal,
                1 - (embedding <=> :query_vector) AS relevance_score
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :query_vector
            LIMIT :top_k
        """)
        
        result = await db.execute(
            stmt,
            {"query_vector": str(query_vector), "top_k": top_k}
        )
        rows = result.fetchall()
        
        documents = self._rows_to_documents(rows)
        logger.info(f"Found {len(documents)} documents via semantic search")
        return documents
    
    async def search_keyword(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[DocumentWithScore]:
        """
        Pure keyword search using only full-text matching.
        
        Use this to compare with hybrid search or when you only
        want exact keyword matches.
        """
        logger.info(f"Keyword search for: '{query}' (top_k={top_k})")
        
        stmt = text("""
            SELECT 
                id, pmid, title, abstract, authors, publication_date, journal,
                ts_rank(search_vector, plainto_tsquery('english', :query_text)) AS relevance_score
            FROM documents
            WHERE search_vector @@ plainto_tsquery('english', :query_text)
            ORDER BY relevance_score DESC
            LIMIT :top_k
        """)
        
        result = await db.execute(
            stmt,
            {"query_text": query, "top_k": top_k}
        )
        rows = result.fetchall()
        
        documents = self._rows_to_documents(rows)
        logger.info(f"Found {len(documents)} documents via keyword search")
        return documents
    
    def _rows_to_documents(self, rows) -> list[DocumentWithScore]:
        """Convert database rows to DocumentWithScore objects."""
        documents = []
        for row in rows:
            doc = DocumentWithScore(
                id=row.id,
                pmid=row.pmid,
                title=row.title,
                abstract=row.abstract,
                authors=row.authors or [],
                publication_date=row.publication_date,
                journal=row.journal,
                relevance_score=float(row.relevance_score),
            )
            documents.append(doc)
        return documents
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def get_document_by_pmid(
        self,
        pmid: str,
        db: AsyncSession,
    ) -> Optional[Document]:
        """
        Fetch a specific document by its PubMed ID.
        
        Useful for getting full document details after search results.
        """
        stmt = select(Document).where(Document.pmid == pmid)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def count_embedded_documents(self, db: AsyncSession) -> int:
        """
        Count how many documents have embeddings.
        
        Useful to check if the database is ready for search.
        """
        stmt = text("SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL")
        result = await db.execute(stmt)
        return result.scalar()
    
    async def count_searchable_documents(self, db: AsyncSession) -> int:
        """
        Count how many documents are ready for hybrid search.
        
        Documents need BOTH embedding and search_vector for hybrid search.
        """
        stmt = text("""
            SELECT COUNT(*) FROM documents 
            WHERE embedding IS NOT NULL AND search_vector IS NOT NULL
        """)
        result = await db.execute(stmt)
        return result.scalar()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def retrieve_documents(
    query: str,
    db: AsyncSession,
    top_k: int = 10,
) -> list[DocumentWithScore]:
    """
    Convenience function for hybrid search (default).
    
    Uses both semantic and keyword search combined.
    
    Example:
        docs = await retrieve_documents("ACE inhibitors mortality", db, top_k=5)
    """
    retriever = Retriever()
    return await retriever.search(query, db, top_k)


async def retrieve_documents_semantic(
    query: str,
    db: AsyncSession,
    top_k: int = 10,
) -> list[DocumentWithScore]:
    """
    Convenience function for pure semantic search.
    
    Example:
        docs = await retrieve_documents_semantic("heart failure treatment", db)
    """
    retriever = Retriever()
    return await retriever.search_semantic(query, db, top_k)


async def retrieve_documents_keyword(
    query: str,
    db: AsyncSession,
    top_k: int = 10,
) -> list[DocumentWithScore]:
    """
    Convenience function for pure keyword search.
    
    Example:
        docs = await retrieve_documents_keyword("ACE inhibitors", db)
    """
    retriever = Retriever()
    return await retriever.search_keyword(query, db, top_k)
