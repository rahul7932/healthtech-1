from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine, Base

# Import models so SQLAlchemy knows about them when creating tables
# Without this import, Base.metadata.create_all() wouldn't know about Document
from app.models.document import Document  # noqa: F401


# =============================================================================
# LIFESPAN: Startup and Shutdown Logic
# =============================================================================
#
# What is lifespan?
# A function that runs code ONCE when the server starts, and ONCE when it stops.
# It's the place to set up resources (database, connections) and clean them up.
#
# How does it work?
# - Everything BEFORE 'yield' runs on startup (server is starting)
# - The 'yield' pauses the function while the server handles requests
# - Everything AFTER 'yield' runs on shutdown (server is stopping)
#
# Think of it like opening and closing a restaurant:
# - Before yield: unlock doors, turn on lights, prep kitchen (startup)
# - yield: restaurant is open, serving customers (handling requests)
# - After yield: clean up, turn off lights, lock doors (shutdown)
#
# Why use lifespan instead of @app.on_event("startup")?
# - @app.on_event is deprecated in newer FastAPI versions
# - lifespan is cleaner — startup and shutdown logic in one place
# - Guarantees cleanup runs even if startup partially fails
#
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    
    # === STARTUP (runs once when server starts) ===
    async with engine.begin() as conn:
        # Enable pgvector extension for embedding similarity search
        # This only needs to run once, but IF NOT EXISTS makes it safe to repeat
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Create all database tables defined in our models
        # If tables already exist, this does nothing (safe to run repeatedly)
        await conn.run_sync(Base.metadata.create_all)
    
    # === YIELD (server is now running and handling requests) ===
    yield
    
    # === SHUTDOWN (runs once when server stops) ===
    # Close all database connections in the pool
    # Important for clean shutdown — prevents connection leaks
    await engine.dispose()


app = FastAPI(
    title="Medical AI Trust Layer",
    description="RAG system with post-hoc verification for medical evidence",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
