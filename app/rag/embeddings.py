"""Embedding backends for ingestion."""

from __future__ import annotations

import hashlib
import math
import warnings
from dataclasses import dataclass

DEFAULT_VECTOR_SIZE = 384


class EmbeddingBackend:
    """Simple embedding backend protocol."""

    vector_size: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


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


def get_embedding_backend(model_name: str) -> EmbeddingBackend:
    """Create sentence-transformers backend, fallback to deterministic dummy embeddings."""

    try:
        return SentenceTransformerEmbedding(model_name=model_name)
    except Exception as exc:
        warnings.warn(
            f"Falling back to DummyEmbedding because sentence-transformers is unavailable: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return DummyEmbedding(vector_size=DEFAULT_VECTOR_SIZE)
