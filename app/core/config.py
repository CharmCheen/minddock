"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

KB_DIR = "knowledge_base"
CHROMA_DIR = "data/chroma"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    app_name: str = "pka"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    kb_dir: str = KB_DIR
    chroma_dir: str = CHROMA_DIR
    embedding_model: str = EMBEDDING_MODEL

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
