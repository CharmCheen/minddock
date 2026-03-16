"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

KB_DIR = "knowledge_base"
CHROMA_DIR = "data/chroma"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_BASE_URL = "https://api.openai.com/v1"
LLM_MODEL = "gpt-4o-mini"
LLM_TIMEOUT_SECONDS = 30.0
RERANK_PROVIDER = "noop"
COMPRESS_PROVIDER = "noop"
WATCH_DEBOUNCE_SECONDS = 1.0
HASH_STORE_PATH = "data/index/file_hashes.json"


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    app_name: str = "MindDock"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    kb_dir: str = KB_DIR
    chroma_dir: str = CHROMA_DIR
    embedding_model: str = EMBEDDING_MODEL
    llm_api_key: str = ""
    llm_base_url: str = LLM_BASE_URL
    llm_model: str = LLM_MODEL
    llm_timeout_seconds: float = LLM_TIMEOUT_SECONDS
    rerank_enabled: bool = False
    compress_enabled: bool = False
    rerank_provider: str = RERANK_PROVIDER
    compress_provider: str = COMPRESS_PROVIDER
    watch_enabled: bool = False
    watch_path: str = KB_DIR
    watch_debounce_seconds: float = WATCH_DEBOUNCE_SECONDS
    watch_recursive: bool = True
    hash_store_path: str = HASH_STORE_PATH

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
