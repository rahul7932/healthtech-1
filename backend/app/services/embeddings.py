"""
OpenAI Embedding Service.

WHAT THIS DOES:
Converts text into vector embeddings using OpenAI's text-embedding-3-small model.
These vectors enable semantic similarity search via pgvector.

WHEN EMBEDDINGS ARE GENERATED:
═══════════════════════════════════════════════════════════════════════════════
Embeddings are generated at INGEST TIME, not query time.

INGEST TIME (runs once when populating database):
    POST /api/documents/ingest {"search_term": "ACE inhibitors"}
        → Fetch articles from PubMed
        → Save to database  
        → Generate embeddings for ALL articles  ← happens here
        → Done. Documents are now searchable.

QUERY TIME (runs every time user asks a question):
    POST /api/query {"question": "Do ACE inhibitors help?"}
        → Embed the QUERY only (1 API call, ~100ms)
        → Search pre-embedded documents via pgvector (instant)
        → Return similar documents

WHY NOT EMBED AT QUERY TIME?
    - Slow: would add seconds to every query
    - Wasteful: same document would be embedded repeatedly
    - Expensive: unnecessary API calls to OpenAI
═══════════════════════════════════════════════════════════════════════════════

HOW IT WORKS:
1. Takes document text (title + abstract)
2. Sends to OpenAI embedding API
3. Returns 1536-dimensional vector
4. Vector gets stored in pgvector for similarity search

BATCHING:
OpenAI allows up to 100 texts per API call. We batch documents
to minimize API calls and costs.

MODEL:
text-embedding-3-small (1536 dimensions, $0.02/1M tokens)
- Good balance of quality and cost
- Matches our pgvector column size

USAGE:
    service = EmbeddingService()
    
    # Single text
    vector = await service.embed_text("ACE inhibitors reduce mortality...")
    
    # Batch of texts
    vectors = await service.embed_texts(["text1", "text2", ...])
    
    # Embed all unembedded documents in database
    count = await service.embed_documents(db_session)
"""

import logging
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import Document

logger = logging.getLogger(__name__)

# OpenAI embedding model
# text-embedding-3-small: 1536 dimensions, good quality, lower cost
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Batch size for OpenAI API (max is 2048, but 100 is safer for memory)
BATCH_SIZE = 100

# Max tokens for embedding model (8191 for text-embedding-3-small)
# We truncate longer texts to avoid errors
MAX_TOKENS = 8000  # Leave some buffer


class EmbeddingService:
    """
    Generate embeddings using OpenAI's API.
    
    This service handles:
    - Single text embedding
    - Batch embedding (more efficient)
    - Database integration (embed all unembedded documents)
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    # =========================================================================
    # CORE EMBEDDING METHODS
    # =========================================================================
    
    async def embed_text(self, text: str) -> list[float]:
        """
        Embed a single text into a vector.
        
        Args:
            text: The text to embed (e.g., article title + abstract)
            
        Returns:
            1536-dimensional vector (list of floats)
            
        Example:
            vector = await service.embed_text("ACE inhibitors reduce mortality...")
            # Returns: [0.023, -0.041, 0.078, ...]  (1536 floats)
        """
        # Truncate if too long (rough estimate: 1 token ≈ 4 chars)
        if len(text) > MAX_TOKENS * 4:
            text = text[:MAX_TOKENS * 4]
            logger.warning(f"Truncated text to {MAX_TOKENS * 4} chars for embedding")
        
        response = await self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        
        return response.data[0].embedding
    
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts in a single API call (more efficient).
        
        OpenAI allows up to 2048 texts per call, but we limit to BATCH_SIZE
        for memory safety. For larger lists, use embed_documents().
        
        Args:
            texts: List of texts to embed (max BATCH_SIZE)
            
        Returns:
            List of vectors, same order as input texts
            
        Example:
            vectors = await service.embed_texts(["text1", "text2"])
            # Returns: [[0.023, ...], [0.045, ...]]
        """
        if not texts:
            return []
        
        if len(texts) > BATCH_SIZE:
            raise ValueError(f"Too many texts ({len(texts)}), max is {BATCH_SIZE}. Use embed_documents() for larger batches.")
        
        # Truncate long texts
        processed_texts = []
        for text in texts:
            if len(text) > MAX_TOKENS * 4:
                text = text[:MAX_TOKENS * 4]
            processed_texts.append(text)
        
        response = await self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=processed_texts,
        )
        
        # Response data is in same order as input
        return [item.embedding for item in response.data]
    
    # =========================================================================
    # DATABASE INTEGRATION
    # =========================================================================
    
    async def embed_documents(self, db: AsyncSession) -> int:
        """
        Find all documents without embeddings and embed them.
        
        This is the main method you'll use after ingesting PubMed articles.
        It processes documents in batches for efficiency.
        
        Args:
            db: Database session
            
        Returns:
            Number of documents embedded
            
        Example:
            # After ingesting PubMed articles:
            service = EmbeddingService()
            count = await service.embed_documents(db)
            print(f"Embedded {count} documents")
        """
        total_embedded = 0
        
        while True:
            # Get batch of documents without embeddings
            stmt = (
                select(Document)
                .where(Document.embedding.is_(None))
                .limit(BATCH_SIZE)
            )
            result = await db.execute(stmt)
            documents = result.scalars().all()
            
            if not documents:
                break  # No more documents to embed
            
            logger.info(f"Embedding batch of {len(documents)} documents...")
            
            # Prepare texts for embedding (title + abstract for better search)
            texts = [
                self._prepare_text_for_embedding(doc)
                for doc in documents
            ]
            
            # Get embeddings from OpenAI
            try:
                embeddings = await self.embed_texts(texts)
            except Exception as e:
                logger.error(f"Failed to embed batch: {e}")
                raise
            
            # Update documents with embeddings
            for doc, embedding in zip(documents, embeddings):
                doc.embedding = embedding
            
            # Commit this batch
            await db.commit()
            
            total_embedded += len(documents)
            logger.info(f"Embedded {total_embedded} documents so far...")
        
        logger.info(f"Finished embedding {total_embedded} documents")
        return total_embedded
    
    async def embed_single_document(self, db: AsyncSession, document: Document) -> None:
        """
        Embed a single document and save to database.
        
        Use this when adding a single new document, rather than
        calling embed_documents() which scans the whole table.
        
        Args:
            db: Database session
            document: Document to embed (will be modified in place)
        """
        text = self._prepare_text_for_embedding(document)
        document.embedding = await self.embed_text(text)
        await db.commit()
    
    def _prepare_text_for_embedding(self, document: Document) -> str:
        """
        Prepare document text for embedding.
        
        We combine title + abstract for better semantic representation.
        The title provides context that helps with search relevance.
        """
        return f"{document.title}\n\n{document.abstract}"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def embed_query(query: str) -> list[float]:
    """
    Embed a search query for similarity search.
    
    WHEN TO USE:
    When a user asks a question, embed it to search for similar documents.
    
    Example:
        query_vector = await embed_query("Do ACE inhibitors reduce mortality?")
        # Then use query_vector for pgvector similarity search
    """
    service = EmbeddingService()
    return await service.embed_text(query)


async def embed_all_documents(db: AsyncSession) -> int:
    """
    Convenience function to embed all unembedded documents.
    
    Example:
        async with async_session() as db:
            count = await embed_all_documents(db)
            print(f"Embedded {count} documents")
    """
    service = EmbeddingService()
    return await service.embed_documents(db)
