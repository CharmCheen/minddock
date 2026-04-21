"""Post-retrieval rerank and compression helpers."""

from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.rag.retrieval_models import RetrievedChunk

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")
_MAX_COMPRESSED_CHARS = 280
_MAX_COMPRESSED_HITS = 4
_MAX_COMPRESSED_SENTENCES = 2


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _WORD_RE.findall(text)]


def _overlap_score(query: str, text: str) -> float:
    query_tokens = set(_tokenize(query))
    text_tokens = _tokenize(text)
    if not query_tokens or not text_tokens:
        return 0.0

    matches = sum(1 for token in text_tokens if token in query_tokens)
    density = matches / max(len(text_tokens), 1)
    coverage = len(query_tokens.intersection(text_tokens)) / max(len(query_tokens), 1)
    return density + coverage


class Reranker(ABC):
    """Rank retrieved hits before context assembly."""

    @abstractmethod
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return reranked hits."""


class Compressor(ABC):
    """Compress retrieved hits before context assembly."""

    @abstractmethod
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return compressed hits."""


class NoOpReranker(Reranker):
    """Pass-through reranker."""

    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class NoOpCompressor(Compressor):
    """Pass-through compressor."""

    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class HeuristicReranker(Reranker):
    """Lightweight reranker that combines lexical overlap with retrieval distance."""

    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        rescored: list[tuple[float, RetrievedChunk]] = []
        for index, hit in enumerate(hits):
            distance = hit.distance
            distance_score = 0.0
            if distance is not None:
                distance_score = 1.0 / (1.0 + max(float(distance), 0.0))

            text = hit.text
            metadata_text = " ".join(
                getattr(hit, field, "").strip()
                for field in ("title", "section", "location", "ref")
            )
            lexical_score = _overlap_score(query, text)
            metadata_score = _overlap_score(query, metadata_text)
            short_bonus = 0.1 / max(math.log(len(text) + 10), 1.0)
            total = (distance_score * 0.45) + (lexical_score * 0.4) + (metadata_score * 0.1) + short_bonus

            updated_hit = hit.with_updates(
                rerank_score=round(total, 6),
                retrieval_rank=index,
            )
            rescored.append((total, updated_hit))

        rescored.sort(key=lambda item: item[0], reverse=True)
        reranked = [hit for _, hit in rescored]
        logger.debug("Heuristic reranker executed: query=%s hit_count=%d", query[:40], len(reranked))
        return reranked


class TrimmingCompressor(Compressor):
    """Trim hits to the most relevant sentences and cap the evidence set size."""

    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        trimmed_hits: list[RetrievedChunk] = []
        for hit in hits[:_MAX_COMPRESSED_HITS]:
            text = hit.text.strip()
            if not text:
                continue

            sentences = [part.strip() for part in _SENTENCE_RE.split(text) if part.strip()]
            if not sentences:
                sentences = [text]

            ranked_sentences = sorted(
                sentences,
                key=lambda sentence: _overlap_score(query, sentence),
                reverse=True,
            )

            kept_sentences: list[str] = []
            total_chars = 0
            for sentence in ranked_sentences:
                if len(kept_sentences) >= _MAX_COMPRESSED_SENTENCES:
                    break
                next_chars = total_chars + len(sentence) + (1 if kept_sentences else 0)
                if kept_sentences and next_chars > _MAX_COMPRESSED_CHARS:
                    break
                kept_sentences.append(sentence)
                total_chars = next_chars
                if total_chars >= _MAX_COMPRESSED_CHARS:
                    break

            compressed_text = " ".join(kept_sentences) if kept_sentences else text[:_MAX_COMPRESSED_CHARS]
            updated_hit = hit.with_updates(
                original_text=text,
                compressed_text=compressed_text,
                text=compressed_text,
                compression_applied=compressed_text != text,
            )
            trimmed_hits.append(updated_hit)

        logger.debug("Compressor executed: query=%s input_hits=%d output_hits=%d", query[:40], len(hits), len(trimmed_hits))
        return trimmed_hits


def get_reranker() -> Reranker:
    """Return the configured reranker implementation."""

    settings = get_settings()
    provider = settings.rerank_provider.strip().lower()
    if not settings.rerank_enabled or provider == "noop":
        return NoOpReranker()
    return HeuristicReranker()


def get_compressor() -> Compressor:
    """Return the configured compressor implementation."""

    settings = get_settings()
    provider = settings.compress_provider.strip().lower()
    if not settings.compress_enabled or provider == "noop":
        return NoOpCompressor()
    return TrimmingCompressor()
