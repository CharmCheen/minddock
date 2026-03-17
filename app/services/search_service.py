"""Application service for minimal vector search."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_backend
from app.rag.vectorstore import search_collection


@dataclass
class SearchService:
    """Minimal service to bridge API requests to Chroma search."""

    def retrieve(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> list[dict[str, object]]:
        settings = get_settings()
        embedder = get_embedding_backend(settings.embedding_model)
        query_embedding = embedder.embed_texts([query])[0]

        raw_hits = search_collection(query_embedding=query_embedding, top_k=top_k, filters=filters)
        hits = []
        for item in raw_hits:
            metadata = item["metadata"]
            hits.append(
                {
                    "text": item["text"],
                    "doc_id": str(metadata.get("doc_id", "")),
                    "chunk_id": str(metadata.get("chunk_id", "")),
                    "source": str(metadata.get("source") or metadata.get("source_path") or ""),
                    "title": str(metadata.get("title") or ""),
                    "section": str(metadata.get("section") or ""),
                    "location": str(metadata.get("location") or metadata.get("section") or metadata.get("source_path") or ""),
                    "ref": str(
                        metadata.get("ref")
                        or metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("source_path")
                        or ""
                    ),
                    "distance": item.get("distance"),
                }
            )

        return hits

    def search(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        hits = self.retrieve(query=query, top_k=top_k, filters=filters)
        return {
            "query": query,
            "top_k": top_k,
            "hits": hits,
        }
