"""Chroma vector store helpers."""

from __future__ import annotations

from app.core.config import get_settings

COLLECTION_NAME = "knowledge_base"


def get_vectorstore():
    """Return a persistent Chroma collection."""

    try:
        import chromadb
    except Exception as exc:
        raise RuntimeError(
            "chromadb is required for ingestion. Install it with `pip install chromadb`."
        ) from exc

    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(name=COLLECTION_NAME)
