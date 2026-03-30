"""Application service for semantic vector search."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.exceptions import SearchError
from app.rag.embeddings import get_embedding_backend
from app.rag.vectorstore import search_collection
from app.services.grounded_generation import build_citation

logger = logging.getLogger(__name__)

SNIPPET_LIMIT = 120


@dataclass
class SearchService:
    """Bridge API requests to Chroma search, returning hits with embedded citations."""

    def retrieve(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> list[dict[str, object]]:
        """Retrieve raw hits from the vector store.

        Each hit dict contains: text, doc_id, chunk_id, source, title,
        section, location, ref, page, anchor, distance.
        """
        settings = get_settings()
        embedder = get_embedding_backend(settings.embedding_model)
        query_embedding = embedder.embed_texts([query])[0]

        raw_hits = search_collection(query_embedding=query_embedding, top_k=top_k, filters=filters)

        logger.debug(
            "Vector search completed: query_preview=%s top_k=%d raw_hits=%d filters=%s",
            query[:60], top_k, len(raw_hits), filters,
        )

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
                    "location": str(
                        metadata.get("location") or metadata.get("section") or metadata.get("source_path") or ""
                    ),
                    "ref": str(
                        metadata.get("ref")
                        or metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("source_path")
                        or ""
                    ),
                    "page": metadata.get("page") or None,
                    "anchor": metadata.get("anchor") or None,
                    "distance": item.get("distance"),
                }
            )

        return hits

    def search(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        """Execute search and return structured response with citation per hit.

        Raises:
            SearchError: If the search pipeline encounters an error.
        """
        try:
            hits = self.retrieve(query=query, top_k=top_k, filters=filters)

            search_hits = []
            for hit in hits:
                citation = build_citation(hit)
                search_hits.append(
                    {
                        "text": hit["text"],
                        "doc_id": hit["doc_id"],
                        "chunk_id": hit["chunk_id"],
                        "source": hit["source"],
                        "distance": hit.get("distance"),
                        "citation": citation,
                    }
                )

            logger.info(
                "Search response built: query_preview=%s hits=%d",
                query[:60], len(search_hits),
            )

            return {
                "query": query,
                "top_k": top_k,
                "hits": search_hits,
            }

        except Exception as exc:
            logger.exception("Search failed: query_preview=%s", query[:60])
            raise SearchError(detail=f"Search failed: {exc}") from exc
