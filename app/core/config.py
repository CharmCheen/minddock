"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

KB_DIR = "knowledge_base"
CHROMA_DIR = "data/chroma"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LOG_DIR = "logs"
LLM_BASE_URL = "https://api.openai.com/v1"
LLM_MODEL = "gpt-4o-mini"
LLM_TIMEOUT_SECONDS = 30.0
RERANK_PROVIDER = "heuristic"
COMPRESS_PROVIDER = "trim"
WATCH_DEBOUNCE_SECONDS = 1.0
HASH_STORE_PATH = "data/index/file_hashes.json"
URL_FETCH_TIMEOUT_SECONDS = 15.0
URL_FETCH_RETRY_COUNT = 1
URL_FETCH_RETRY_BACKOFF_SECONDS = 0.5
URL_FETCH_VERIFY_SSL = True
URL_FETCH_ALLOW_INSECURE_FALLBACK = False
URL_FETCH_USER_AGENT = "MindDock/0.1 (+https://example.invalid/minddock)"
REBUILD_RETRY_SECONDS = 0.75
REBUILD_MAX_RETRIES = 3
RUNTIME_PROFILES_JSON = ""
RUN_CONTROL_MAX_RUNS = 100
RUN_CONTROL_RECENT_EVENT_BUFFER_SIZE = 100
RUN_CONTROL_COMPLETED_RUN_TTL_SECONDS = 300
RUN_CONTROL_HEARTBEAT_INTERVAL_SECONDS = 5


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    app_name: str = "MindDock"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_dir: str = LOG_DIR
    kb_dir: str = KB_DIR
    chroma_dir: str = CHROMA_DIR
    embedding_model: str = EMBEDDING_MODEL
    llm_api_key: str = ""
    llm_base_url: str = LLM_BASE_URL
    llm_model: str = LLM_MODEL
    llm_timeout_seconds: float = LLM_TIMEOUT_SECONDS
    rerank_enabled: bool = True
    compress_enabled: bool = True
    rerank_provider: str = RERANK_PROVIDER
    compress_provider: str = COMPRESS_PROVIDER
    # Hybrid retrieval (dense + BM25 + RRF)
    hybrid_retrieval_enabled: bool = False
    bm25_top_k: int = 50
    rrf_k: int = 60
    watch_enabled: bool = False
    watch_path: str = KB_DIR
    watch_debounce_seconds: float = WATCH_DEBOUNCE_SECONDS
    watch_recursive: bool = True
    hash_store_path: str = HASH_STORE_PATH
    url_fetch_timeout_seconds: float = URL_FETCH_TIMEOUT_SECONDS
    url_fetch_retry_count: int = URL_FETCH_RETRY_COUNT
    url_fetch_retry_backoff_seconds: float = URL_FETCH_RETRY_BACKOFF_SECONDS
    url_fetch_verify_ssl: bool = URL_FETCH_VERIFY_SSL
    url_fetch_allow_insecure_fallback: bool = URL_FETCH_ALLOW_INSECURE_FALLBACK
    url_fetch_user_agent: str = URL_FETCH_USER_AGENT
    rebuild_retry_seconds: float = REBUILD_RETRY_SECONDS
    rebuild_max_retries: int = REBUILD_MAX_RETRIES
    runtime_profiles_json: str = RUNTIME_PROFILES_JSON
    run_control_max_runs: int = RUN_CONTROL_MAX_RUNS
    run_control_recent_event_buffer_size: int = RUN_CONTROL_RECENT_EVENT_BUFFER_SIZE
    run_control_completed_run_ttl_seconds: int = RUN_CONTROL_COMPLETED_RUN_TTL_SECONDS
    run_control_heartbeat_interval_seconds: int = RUN_CONTROL_HEARTBEAT_INTERVAL_SECONDS

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
