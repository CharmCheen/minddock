"""Chroma vector store helpers."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings

COLLECTION_NAME = "knowledge_base"
SUPPORTED_FILTER_FIELDS = {"source", "section"}


@lru_cache
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


def _build_where(filters: dict[str, str] | None) -> dict[str, str] | None:
    """Normalize supported metadata filters for Chroma `where` queries."""

    if not filters:
        return None

    where: dict[str, str] = {}
    for key, value in filters.items():
        if key not in SUPPORTED_FILTER_FIELDS:
            continue
        normalized = str(value).strip()
        if normalized:
            where[key] = normalized

    return where or None


def search_collection(
    query_embedding: list[float],
    top_k: int,
    filters: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Search the persistent Chroma collection and normalize the results."""

    collection = get_vectorstore()
    total = collection.count()
    if total == 0:
        return []

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, total),
        include=["documents", "metadatas", "distances"],
        where=_build_where(filters),
    )

    documents = result.get("documents") or [[]]
    metadatas = result.get("metadatas") or [[]]
    distances = result.get("distances") or [[]]

    hits: list[dict[str, object]] = []
    for index, text in enumerate(documents[0]):
        metadata = metadatas[0][index] or {}
        distance = distances[0][index] if distances and distances[0] else None
        hits.append(
            {
                "text": text,
                "metadata": metadata,
                "distance": distance,
            }
        )

    return hits


def delete_document(doc_id: str) -> int:
    """Delete all chunks for a single document id and return the deleted chunk count."""

    collection = get_vectorstore()
    result = collection.get(where={"doc_id": doc_id}, include=[])
    ids = result.get("ids") or []
    if not ids:
        return 0

    collection.delete(where={"doc_id": doc_id})
    return len(ids)


def count_document_chunks(doc_id: str) -> int:
    """Return the number of chunks currently stored for a document id."""

    collection = get_vectorstore()
    result = collection.get(where={"doc_id": doc_id}, include=[])
    ids = result.get("ids") or []
    return len(ids)
