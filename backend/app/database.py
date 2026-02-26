"""
Database connection using SQLAlchemy + asyncpg.

Why SQLAlchemy instead of the Supabase Python client?
- Supabase IS PostgreSQL under the hood — we connect directly to it
- pgvector operations (embedding similarity search) need raw SQL access
- SQLAlchemy gives us full control for complex queries and batch operations
- Portable: if we switch from Supabase to another Postgres host, zero code changes

The Supabase client (supabase-py) is better for their auth/storage/realtime features,
but for a RAG system with vector search, direct PostgreSQL access is the standard approach.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

# Load configuration (database URL, API keys) from environment variables
settings = get_settings()

# Connection pool to Supabase PostgreSQL
# - Reuses connections instead of opening a new one per query (much faster)
# - echo=True logs all SQL statements (useful for debugging, disable in production)
engine = create_async_engine(settings.database_url, echo=True)

# Factory that creates database sessions
#
# What is a session? Think of it like a shopping cart:
# - Session starts → you get an empty cart
# - session.add(doc) → item goes in cart (not saved yet)
# - session.commit() → checkout, changes are saved to database
# - session.rollback() → abandon cart, nothing saved
# - Session ends → cart returned, connection goes back to pool
#
# Why use sessions?
# - Transactions: group operations so all succeed or all fail together
# - Change tracking: only saves what you actually modified
# - Rollback: if something fails, undo all uncommitted changes
#
# expire_on_commit=False keeps objects usable after commit (needed for async)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency that yields a database session."""
    async with async_session() as session:
        yield session
