"""
Document Retriever Service.

WHAT THIS DOES:
Finds the most relevant documents for a given query using vector similarity search.

HOW IT WORKS:
1. User asks: "Do ACE inhibitors reduce mortality?"
2. We embed the query → 1536-dim vector
3. pgvector finds documents with similar embeddings (cosine similarity)
4. Return top-K most relevant documents

pgvector OPERATORS:
- <-> : L2 distance (Euclidean)
- <#> : Inner product (negative, for max inner product search)  
- <=> : Cosine distance (what we use - best for text similarity)

Cosine distance = 1 - cosine_similarity
So lower distance = more similar (we ORDER BY distance ASC)

USAGE:
    retriever = Retriever()
    
    # Search by query string (embeds automatically)
    results = await retriever.search("ACE inhibitors heart failure", db, top_k=10)
    
    # Search by pre-computed vector (if you already have it)
    results = await retriever.search_by_vector(query_vector, db, top_k=10)
"""

import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.schemas import DocumentWithScore
from app.services.embeddings import embed_query

logger = logging.getLogger(__name__)


class Retriever:
    """
    Retrieves relevant documents using pgvector similarity search.
    
    This is the core of the RAG system - it finds documents that are
    semantically similar to the user's query.
    """
    
    # =========================================================================
    # MAIN SEARCH METHODS
    # =========================================================================
    
    async def search(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[DocumentWithScore]:
        """
        Search for documents similar to the query.
        
        This is the main method you'll use. It:
        1. Embeds the query using OpenAI
        2. Searches pgvector for similar documents
        3. Returns documents with relevance scores
        
        Args:
            query: The search query (e.g., "Do ACE inhibitors reduce mortality?")
            db: Database session
            top_k: Number of results to return (default: 10)
            
        Returns:
            List of DocumentWithScore, ordered by relevance (most relevant first)
            
        Example:
            retriever = Retriever()
            results = await retriever.search(
                "heart failure treatment options",
                db,
                top_k=5
            )
            for doc in results:
                print(f"{doc.relevance_score:.2f}: {doc.title}")
        """
        logger.info(f"Searching for: '{query}' (top_k={top_k})")
        
        # Step 1: Embed the query
        query_vector = await embed_query(query)
        
        # Step 2: Search by vector
        return await self.search_by_vector(query_vector, db, top_k)
    
    async def search_by_vector(
        self,
        query_vector: list[float],
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[DocumentWithScore]:
        """
        Search for documents similar to a pre-computed vector.
        
        Use this if you've already embedded the query (saves an API call).
        
        Args:
            query_vector: 1536-dimensional embedding vector
            db: Database session
            top_k: Number of results to return
            
        Returns:
            List of DocumentWithScore, ordered by relevance
            
        HOW THE QUERY WORKS:
        We use pgvector's <=> operator for cosine distance.
        
        Cosine distance = 1 - cosine_similarity
        - Distance 0 = identical (similarity 1.0)
        - Distance 1 = orthogonal (similarity 0.0)  
        - Distance 2 = opposite (similarity -1.0)
        
        We convert to similarity score: score = 1 - distance
        """
        # Build the vector search query
        # pgvector uses <=> for cosine distance
        # We order by distance (ascending) to get most similar first
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
        
        logger.info(f"Found {len(documents)} documents")
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


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def retrieve_documents(
    query: str,
    db: AsyncSession,
    top_k: int = 10,
) -> list[DocumentWithScore]:
    """
    Convenience function to search for documents.
    
    WHEN TO USE:
    In API routes or when you don't need to reuse the Retriever instance.
    
    Example:
        docs = await retrieve_documents("ACE inhibitors mortality", db, top_k=5)
    """
    retriever = Retriever()
    return await retriever.search(query, db, top_k)
