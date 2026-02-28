from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Supabase Database
    # Format: postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
    # Default empty string allows tests to run without .env, but app will fail at runtime if not set
    database_url: str = ""

    # OpenAI
    openai_api_key: str = ""

    # PubMed (optional - increases rate limit)
    pubmed_api_key: str = ""

    # Hybrid Search
    # Balance between semantic (vector) and keyword (full-text) search
    # 1.0 = pure semantic, 0.0 = pure keyword, 0.7 = 70% semantic + 30% keyword
    hybrid_search_alpha: float = 0.7

    # Live PubMed Fetch
    # Coverage threshold: minimum average relevance score to consider coverage sufficient
    # If below this, live_fetch will trigger PubMed retrieval
    coverage_threshold: float = 0.6
    
    # Maximum documents to fetch from PubMed when live_fetch is triggered
    live_fetch_max_results: int = 50

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
