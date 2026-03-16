"""Factory for choosing the active LLM provider."""

from __future__ import annotations

from app.core.config import get_settings
from app.llm.mock import MockLLM
from app.llm.openai_compatible import FallbackLLM, OpenAICompatibleLLM
from ports.llm import LLMProvider


def get_llm_provider() -> LLMProvider:
    """Return the configured provider, with MockLLM as default/fallback."""

    settings = get_settings()
    mock = MockLLM()
    if not settings.llm_api_key.strip():
        return mock

    real = OpenAICompatibleLLM(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    return FallbackLLM(primary=real, fallback=mock)
