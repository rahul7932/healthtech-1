"""
SQLAlchemy model for the documents table.

This table stores PubMed abstracts along with their vector embeddings
for similarity search using pgvector.
"""

from datetime import datetime, date
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Date, DateTime, ARRAY
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Document(Base):
    """
    A medical document (PubMed abstract) with its embedding.
    
    The embedding column uses pgvector's Vector type for efficient
    similarity search. We use OpenAI's text-embedding-3-small which
    produces 1536-dimensional vectors.
    """
    
    __tablename__ = "documents"
    
    # Primary key - auto-incrementing integer
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # PubMed ID - unique identifier from PubMed (e.g., "12345678")
    pmid: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    
    # Document content
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text)
    
    # Metadata
    authors: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Vector embedding for semantic similarity search
    # 1536 dimensions = OpenAI text-embedding-3-small output size
    # This is what powers the "find similar documents" functionality
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    
    # Full-text search vector for keyword search (hybrid search)
    # Populated via database trigger on insert/update
    # Contains stemmed tokens from title + abstract
    search_vector = mapped_column(TSVECTOR, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<Document pmid={self.pmid} title={self.title[:50]}...>"
