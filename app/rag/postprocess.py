"""Post-retrieval extension points for rerank and compress."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Reranker(ABC):
    """Rank retrieved hits before context assembly."""

    @abstractmethod
    def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        """Return reranked hits."""


class Compressor(ABC):
    """Compress retrieved hits before context assembly."""

    @abstractmethod
    def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        """Return compressed hits."""


class NoOpReranker(Reranker):
    """Pass-through reranker placeholder."""

    def __init__(self, enabled: bool, provider: str) -> None:
        self._enabled = enabled
        self._provider = provider

    def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        if self._enabled:
            logger.info("NoOp reranker executed: provider=%s hit_count=%s", self._provider, len(hits))
        return hits


class NoOpCompressor(Compressor):
    """Pass-through compressor placeholder."""

    def __init__(self, enabled: bool, provider: str) -> None:
        self._enabled = enabled
        self._provider = provider

    def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        if self._enabled:
            logger.info("NoOp compressor executed: provider=%s hit_count=%s", self._provider, len(hits))
        return hits


def get_reranker() -> Reranker:
    """Return the configured reranker placeholder."""

    settings = get_settings()
    return NoOpReranker(
        enabled=settings.rerank_enabled,
        provider=settings.rerank_provider,
    )


def get_compressor() -> Compressor:
    """Return the configured compressor placeholder."""

    settings = get_settings()
    return NoOpCompressor(
        enabled=settings.compress_enabled,
        provider=settings.compress_provider,
    )
