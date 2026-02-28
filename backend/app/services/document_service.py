"""
Document Service — Handles document storage and retrieval operations.

WHAT THIS DOES:
Provides a clean interface for saving, retrieving, and managing documents
in the database. Used by both the API routes and the QueryPipeline.

WHY THIS EXISTS:
- DRY: Both /documents/ingest and live fetch need to save articles
- Single responsibility: Database operations in one place
- Testable: Easy to mock for unit tests
"""

import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Service for document storage operations.
    
    Handles:
    - Saving articles from PubMed (with deduplication)
    - Counting documents
    - Retrieving documents by PMID
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def save_articles(self, articles: list[dict]) -> int:
        """
        Save articles to the database, skipping duplicates.
        
        Args:
            articles: List of article dicts with keys:
                - pmid (required)
                - title (required)
                - abstract (required)
                - authors (optional)
                - publication_date (optional)
                - journal (optional)
                
        Returns:
            Number of new articles saved (duplicates are skipped)
        """
        saved_count = 0
        
        for article in articles:
            existing = await self.db.execute(
                select(Document).where(Document.pmid == article["pmid"])
            )
            if existing.scalar_one_or_none():
                continue
            
            doc = Document(
                pmid=article["pmid"],
                title=article["title"],
                abstract=article["abstract"],
                authors=article.get("authors"),
                publication_date=article.get("publication_date"),
                journal=article.get("journal"),
            )
            self.db.add(doc)
            saved_count += 1
        
        await self.db.commit()
        
        if saved_count > 0:
            logger.info(f"Saved {saved_count} new documents to database")
        
        return saved_count
    
    async def get_by_pmid(self, pmid: str) -> Optional[Document]:
        """Get a document by its PubMed ID."""
        result = await self.db.execute(
            select(Document).where(Document.pmid == pmid)
        )
        return result.scalar_one_or_none()
    
    async def count(self) -> dict:
        """
        Get document counts.
        
        Returns:
            Dict with keys: total, embedded, pending
        """
        total_result = await self.db.execute(
            select(func.count(Document.id))
        )
        total = total_result.scalar()
        
        embedded_result = await self.db.execute(
            select(func.count(Document.id)).where(Document.embedding.isnot(None))
        )
        embedded = embedded_result.scalar()
        
        return {
            "total": total,
            "embedded": embedded,
            "pending": total - embedded,
        }


async def save_articles(articles: list[dict], db: AsyncSession) -> int:
    """Convenience function to save articles."""
    service = DocumentService(db)
    return await service.save_articles(articles)
