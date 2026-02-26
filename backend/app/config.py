from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://healthtech:healthtech_dev@localhost:5432/healthtech"

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
