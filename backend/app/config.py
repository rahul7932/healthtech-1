from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Supabase Database
    # Format: postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
    database_url: str

    # OpenAI
    openai_api_key: str = ""

    # PubMed (optional - increases rate limit)
    pubmed_api_key: str = ""

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
