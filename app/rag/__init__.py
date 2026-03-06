"""RAG ingestion package."""

from .embeddings import get_embedding_backend
from .splitter import split_text
from .vectorstore import get_vectorstore

__all__ = ["get_embedding_backend", "get_vectorstore", "split_text"]
