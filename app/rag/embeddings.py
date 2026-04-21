"""Embedding backends for ingestion and retrieval."""

from __future__ import annotations

import hashlib
import math
import warnings
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings

DEFAULT_VECTOR_SIZE = 384


class EmbeddingBackend:
    """Simple embedding backend protocol with LangChain compatibility."""

    vector_size: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        return vectors[0] if vectors else [0.0] * self.vector_size

    def as_langchain_embeddings(self):
        return _EmbeddingAdapter(self)


class _EmbeddingAdapter:
    """Wrap a backend in the interface LangChain vector stores expect."""

    def __init__(self, backend: EmbeddingBackend) -> None:
        self._backend = backend

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._backend.embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._backend.embed_query(text)


@dataclass
class DummyEmbedding(EmbeddingBackend):
    """Deterministic hash-based fallback embedding."""

    vector_size: int = DEFAULT_VECTOR_SIZE

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.vector_size
            units = text.split() or list(text)
            if not units:
                vectors.append(vec)
                continue

            for unit in units:
                digest = hashlib.sha256(unit.encode("utf-8", errors="ignore")).digest()
                idx = int.from_bytes(digest[:4], "little") % self.vector_size
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[idx] += sign

            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class SentenceTransformerEmbedding(EmbeddingBackend):
    """Sentence-transformers embedding implementation."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.vector_size = self._model.get_sentence_embedding_dimension() or DEFAULT_VECTOR_SIZE

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return encoded.tolist()


class OpenAIEmbedding(EmbeddingBackend):
    """LangChain OpenAI embedding backend for OpenAI-compatible APIs."""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._embeddings = OpenAIEmbeddings(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            request_timeout=timeout_seconds,
        )
        self.vector_size = DEFAULT_VECTOR_SIZE

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)

    def as_langchain_embeddings(self):
        return self._embeddings


def _looks_like_remote_embedding_model(model_name: str) -> bool:
    lowered = model_name.strip().lower()
    return lowered.startswith("text-embedding-") or lowered.startswith("embedding-")


@lru_cache(maxsize=8)
def get_embedding_backend(model_name: str | None = None) -> EmbeddingBackend:
    """Create the preferred embedding backend with graceful local fallback."""

    settings = get_settings()
    resolved_model_name = model_name or settings.embedding_model

    if settings.llm_api_key.strip() and _looks_like_remote_embedding_model(resolved_model_name):
        try:
            return OpenAIEmbedding(
                model_name=resolved_model_name,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout_seconds=settings.llm_timeout_seconds,
            )
        except Exception as exc:
            warnings.warn(
                f"Falling back to local embeddings because remote embedding init failed: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )

    try:
        return SentenceTransformerEmbedding(model_name=resolved_model_name)
    except Exception as exc:
        warnings.warn(
            f"Falling back to DummyEmbedding because sentence-transformers is unavailable: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return DummyEmbedding(vector_size=DEFAULT_VECTOR_SIZE)
