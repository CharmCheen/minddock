"""LangChain-first Chroma helpers with compatibility wrappers."""

from __future__ import annotations

import gc
import logging
from threading import Lock

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_backend
from app.rag.source_models import (
    CatalogQuery,
    ReplaceDocumentResult,
    SourceCatalogEntry,
    SourceChunkPage,
    SourceChunkPreview,
    SourceDetail,
    SourceInspectResult,
    SourceState,
)
from app.rag.retrieval_models import RetrievalFilters, RetrievedChunk

COLLECTION_NAME = "knowledge_base"

logger = logging.getLogger(__name__)
_VECTORSTORE_CACHE: "LangChainChromaStore | None" = None
_VECTORSTORE_LOCK = Lock()
DEFAULT_CHUNK_PREVIEW_LENGTH = 220


class LangChainChromaStore:
    """Project-facing wrapper around langchain_chroma.Chroma."""

    def __init__(self) -> None:
        from langchain_chroma import Chroma

        settings = get_settings()
        self._store = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=settings.chroma_dir,
            embedding_function=get_embedding_backend(settings.embedding_model).as_langchain_embeddings(),
        )

    def count(self) -> int:
        return self._store._collection.count()

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        if not ids:
            return

        if embeddings is None:
            settings = get_settings()
            embeddings = get_embedding_backend(settings.embedding_model).embed_texts(documents)

        payload: dict[str, object] = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "embeddings": embeddings,
        }
        self._store._collection.upsert(**payload)

    def upsert_documents(self, documents) -> None:
        if not documents:
            return

        ids = [str(doc.metadata["chunk_id"]) for doc in documents]
        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        self.upsert(ids=ids, documents=texts, metadatas=metadatas)

    def list_document_chunk_ids(self, doc_id: str) -> list[str]:
        result = self._store.get(where={"doc_id": doc_id}, include=[])
        return list(result.get("ids") or [])

    def delete_ids(self, ids: list[str]) -> int:
        if not ids:
            return 0
        self._store.delete(ids=ids)
        return len(ids)

    def replace_document(
        self,
        *,
        doc_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]] | None = None,
    ) -> ReplaceDocumentResult:
        existing_ids = set(self.list_document_chunk_ids(doc_id))
        new_ids = set(ids)

        if ids:
            self.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

        deleted = self.delete_ids(sorted(existing_ids - new_ids))
        if not ids and existing_ids:
            deleted += self.delete_ids(sorted(new_ids & existing_ids))

        return ReplaceDocumentResult(upserted=len(ids), deleted=deleted)

    def search_by_text(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        total = self.count()
        if total == 0:
            return []

        effective_k = _candidate_fetch_k(total=total, top_k=top_k, filters=filters)
        results = self._store.similarity_search_with_score(
            query=query,
            k=effective_k,
            filter=_build_where(filters),
        )
        hits = [
            RetrievedChunk.from_raw(doc.page_content, doc.metadata, score)
            for doc, score in results
        ]
        return _apply_post_filters(hits, filters)[:top_k]

    def search_by_vector(
        self,
        query_embedding: list[float],
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        total = self.count()
        if total == 0:
            return []

        effective_k = _candidate_fetch_k(total=total, top_k=top_k, filters=filters)
        result = self._store._collection.query(
            query_embeddings=[query_embedding],
            n_results=effective_k,
            include=["documents", "metadatas", "distances"],
            where=_build_where(filters),
        )

        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]

        hits: list[RetrievedChunk] = []
        max_index = len(documents[0]) if documents else 0
        for index in range(max_index):
            text = documents[0][index] if documents and documents[0] else ""
            metadata = metadatas[0][index] if metadatas and metadatas[0] and index < len(metadatas[0]) else {}
            distance = distances[0][index] if distances and distances[0] and index < len(distances[0]) else None
            hits.append(RetrievedChunk.from_raw(text, metadata, distance))

        return _apply_post_filters(hits, filters)[:top_k]

    def delete_document(self, doc_id: str) -> int:
        result = self._store.get(where={"doc_id": doc_id}, include=[])
        ids = result.get("ids") or []
        if not ids:
            return 0

        self._store.delete(where={"doc_id": doc_id})
        return len(ids)

    def count_document_chunks(self, doc_id: str) -> int:
        result = self._store.get(where={"doc_id": doc_id}, include=[])
        ids = result.get("ids") or []
        return len(ids)

    def list_sources(self, query: CatalogQuery | None = None) -> list[SourceCatalogEntry]:
        details = self.list_source_details(query=query)
        return [detail.entry for detail in details]

    def list_source_details(self, query: CatalogQuery | None = None) -> list[SourceDetail]:
        where = {"source_type": query.source_type} if query and query.source_type else None
        result = self._store.get(where=where, include=["metadatas"])
        metadatas = result.get("metadatas") or []
        grouped: dict[str, list[dict[str, object]]] = {}
        for metadata in metadatas:
            metadata = metadata or {}
            doc_id = str(metadata.get("doc_id") or "").strip()
            if not doc_id:
                continue
            grouped.setdefault(doc_id, []).append(dict(metadata))

        details = [_build_source_detail(rows) for rows in grouped.values() if rows]
        details.sort(key=lambda item: (item.entry.source.lower(), item.entry.title.lower(), item.entry.doc_id))
        return details

    def inspect_source(
        self,
        doc_id: str,
        *,
        limit: int,
        offset: int,
        include_admin_metadata: bool = False,
    ) -> SourceInspectResult | None:
        result = self._store.get(where={"doc_id": doc_id}, include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        if not metadatas:
            return None

        rows = [
            {
                "metadata": dict(metadata or {}),
                "document": str(document or ""),
            }
            for metadata, document in zip(metadatas, documents, strict=True)
        ]
        rows.sort(key=_chunk_sort_key)
        detail = _build_source_detail([row["metadata"] for row in rows])
        page_rows = rows[offset : offset + limit]
        previews = [
            _build_chunk_preview(row, include_admin_metadata=include_admin_metadata)
            for row in page_rows
        ]
        admin_metadata = _build_source_admin_metadata(detail) if include_admin_metadata else {}
        return SourceInspectResult(
            detail=detail,
            chunk_page=SourceChunkPage(
                total_chunks=len(rows),
                returned_chunks=len(previews),
                limit=limit,
                offset=offset,
                chunks=previews,
            ),
            include_admin_metadata=include_admin_metadata,
            admin_metadata=admin_metadata,
        )

    def as_retriever(self, search_kwargs: dict[str, object] | None = None):
        return self._store.as_retriever(search_kwargs=search_kwargs or {})

    def close(self) -> None:
        """Best-effort release of Chroma resources for rebuilds on Windows."""

        store = self._store
        client = getattr(store, "_client", None)
        try:
            system = getattr(client, "_system", None)
            if system is not None and hasattr(system, "stop"):
                system.stop()
        except Exception:
            logger.debug("Failed to stop Chroma system cleanly", exc_info=True)
        self._store = None  # type: ignore[assignment]


def get_vectorstore():
    """Return a persistent LangChain Chroma wrapper."""

    global _VECTORSTORE_CACHE
    with _VECTORSTORE_LOCK:
        if _VECTORSTORE_CACHE is None:
            try:
                _VECTORSTORE_CACHE = LangChainChromaStore()
            except Exception as exc:
                raise RuntimeError(
                    "langchain-chroma and chromadb are required for vector storage."
                ) from exc
        return _VECTORSTORE_CACHE


def clear_vectorstore_cache() -> None:
    """Clear the cached vector store so rebuilds recreate the client."""

    global _VECTORSTORE_CACHE
    with _VECTORSTORE_LOCK:
        if _VECTORSTORE_CACHE is not None:
            try:
                _VECTORSTORE_CACHE.close()
            finally:
                _VECTORSTORE_CACHE = None
    gc.collect()


def _build_where(filters: RetrievalFilters | dict[str, object] | None) -> dict[str, str] | None:
    """Normalize supported metadata filters for Chroma `where` queries.

    Accepts ``RetrievalFilters`` as the formal path and a legacy mapping as a
    compatibility fallback for older tests and utility code.
    """

    if not filters:
        return None

    if isinstance(filters, dict):
        filters = RetrievalFilters(
            sources=_as_tuple(filters.get("source")),
            source_types=_as_tuple(filters.get("source_type")),
            section=filters.get("section"),
        )

    where: dict[str, str] = {}
    if filters.section:
        where["section"] = filters.section
    single_source = filters.normalized_single_source()
    if single_source:
        where["source"] = single_source
    single_source_type = filters.normalized_single_source_type()
    if single_source_type:
        where["source_type"] = single_source_type

    return where or None


def _candidate_fetch_k(*, total: int, top_k: int, filters: RetrievalFilters | None) -> int:
    if not filters:
        return min(top_k, total)

    needs_post_filter = (
        len(filters.sources) > 1
        or len(filters.source_types) > 1
        or filters.title_contains is not None
        or filters.requested_url_contains is not None
        or filters.page_from is not None
        or filters.page_to is not None
    )
    if not needs_post_filter:
        return min(top_k, total)
    return min(max(top_k * 10, 20), total)


def _apply_post_filters(hits: list[RetrievedChunk], filters: RetrievalFilters | None) -> list[RetrievedChunk]:
    if not filters:
        return hits
    return [hit for hit in hits if filters.matches_metadata(_chunk_to_metadata(hit))]


def _chunk_to_metadata(hit: RetrievedChunk) -> dict[str, object]:
    metadata = {
        "source": hit.source,
        "source_type": hit.source_type,
        "section": hit.section,
        "title": hit.title,
        "page": hit.page,
        "requested_url": hit.requested_url,
    }
    metadata.update(hit.extra_metadata)
    return metadata


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


def search_collection(
    query_embedding: list[float],
    top_k: int,
    filters: RetrievalFilters | None = None,
) -> list[RetrievedChunk]:
    """Search the persistent Chroma store and normalize the results."""

    return get_vectorstore().search_by_vector(
        query_embedding=query_embedding,
        top_k=top_k,
        filters=filters,
    )


def delete_document(doc_id: str) -> int:
    """Delete all chunks for a single document id and return the deleted chunk count."""

    return get_vectorstore().delete_document(doc_id)


def count_document_chunks(doc_id: str) -> int:
    """Return the number of chunks currently stored for a document id."""

    return get_vectorstore().count_document_chunks(doc_id)


def replace_document(
    *,
    doc_id: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, str]],
    embeddings: list[list[float]] | None = None,
) -> ReplaceDocumentResult:
    """Upsert a document's current chunks and delete stale chunk ids."""

    return get_vectorstore().replace_document(
        doc_id=doc_id,
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def list_sources(query: CatalogQuery | None = None) -> list[SourceCatalogEntry]:
    """List indexed sources aggregated from vector-store chunk metadata."""

    return get_vectorstore().list_sources(query=query)


def list_source_details(query: CatalogQuery | None = None) -> list[SourceDetail]:
    """List indexed source details aggregated from vector-store chunk metadata."""

    return get_vectorstore().list_source_details(query=query)


def inspect_source(
    doc_id: str,
    *,
    limit: int,
    offset: int,
    include_admin_metadata: bool = False,
) -> SourceInspectResult | None:
    """Return source summary plus paginated chunk previews."""

    return get_vectorstore().inspect_source(
        doc_id,
        limit=limit,
        offset=offset,
        include_admin_metadata=include_admin_metadata,
    )


def _build_source_detail(rows: list[dict[str, object]]) -> SourceDetail:
    representative = rows[0]
    doc_id = str(representative.get("doc_id") or "")
    source = str(representative.get("source") or representative.get("source_path") or "")
    source_type = str(representative.get("source_type") or "file")
    title = str(representative.get("title") or source)
    sections = tuple(sorted({str(row.get("section") or "").strip() for row in rows if str(row.get("section") or "").strip()}))
    pages = tuple(sorted({int(row.get("page")) for row in rows if str(row.get("page") or "").strip().isdigit()}))
    requested_url = _first_non_empty(rows, "requested_url")
    final_url = _first_non_empty(rows, "final_url")
    domain = _first_non_empty(rows, "domain")
    description = _first_non_empty(rows, "og_description")
    representative_metadata = {
        key: value
        for key, value in representative.items()
        if key not in {"chunk_id", "doc_id"}
    }
    return SourceDetail(
        entry=SourceCatalogEntry(
            doc_id=doc_id,
            source=source,
            source_type=source_type,
            title=title,
            chunk_count=len(rows),
            sections=sections,
            pages=pages,
            requested_url=requested_url,
            final_url=final_url,
            state=SourceState(
                doc_id=doc_id,
                source=source,
                current_version=_first_non_empty(rows, "source_version") or _first_non_empty(rows, "content_hash"),
                content_hash=_first_non_empty(rows, "content_hash"),
                last_ingested_at=_first_non_empty(rows, "last_ingested_at"),
                chunk_count=len(rows),
                ingest_status=_first_non_empty(rows, "ingest_status") or "ready",
            ),
            domain=domain,
            description=description,
        ),
        representative_metadata=representative_metadata,
    )


def _first_non_empty(rows: list[dict[str, object]], key: str) -> str | None:
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return None


def _chunk_sort_key(row: dict[str, object]) -> tuple[int, str]:
    metadata = row["metadata"]
    chunk_id = str(metadata.get("chunk_id") or "")
    chunk_index = _extract_chunk_index(chunk_id)
    return (chunk_index if chunk_index is not None else 10**9, chunk_id)


def _extract_chunk_index(chunk_id: str) -> int | None:
    _, _, suffix = chunk_id.rpartition(":")
    if suffix.isdigit():
        return int(suffix)
    return None


def _preview_text(text: str, *, max_chars: int = DEFAULT_CHUNK_PREVIEW_LENGTH) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _build_chunk_preview(
    row: dict[str, object],
    *,
    include_admin_metadata: bool,
) -> SourceChunkPreview:
    metadata = row["metadata"]
    chunk_id = str(metadata.get("chunk_id") or "")
    admin_metadata = {}
    if include_admin_metadata:
        admin_metadata = {
            "doc_id": str(metadata.get("doc_id") or ""),
            "source_type": str(metadata.get("source_type") or ""),
        }
        requested_url = str(metadata.get("requested_url") or "").strip()
        final_url = str(metadata.get("final_url") or "").strip()
        if requested_url:
            admin_metadata["requested_url"] = requested_url
        if final_url:
            admin_metadata["final_url"] = final_url

    return SourceChunkPreview(
        chunk_id=chunk_id,
        chunk_index=_extract_chunk_index(chunk_id),
        preview_text=_preview_text(str(row.get("document") or "")),
        title=str(metadata.get("title") or ""),
        section=str(metadata.get("section") or "").strip() or None,
        section_path=str(metadata.get("section_path") or "").strip() or None,
        location=str(metadata.get("location") or "").strip() or None,
        ref=str(metadata.get("ref") or "").strip() or None,
        page=int(str(metadata.get("page"))) if str(metadata.get("page") or "").strip().isdigit() else None,
        anchor=str(metadata.get("anchor") or "").strip() or None,
        admin_metadata=admin_metadata,
    )


def _build_source_admin_metadata(detail: SourceDetail) -> dict[str, object]:
    entry = detail.entry
    metadata = {
        "doc_id": entry.doc_id,
        "source": entry.source,
        "source_type": entry.source_type,
        "chunk_count": entry.chunk_count,
        "representative_metadata": detail.representative_metadata,
        "source_state": None if entry.state is None else {
            "doc_id": entry.state.doc_id,
            "source": entry.state.source,
            "current_version": entry.state.current_version,
            "content_hash": entry.state.content_hash,
            "last_ingested_at": entry.state.last_ingested_at,
            "chunk_count": entry.state.chunk_count,
            "ingest_status": entry.state.ingest_status,
        },
    }
    if entry.requested_url:
        metadata["requested_url"] = entry.requested_url
    if entry.final_url:
        metadata["final_url"] = entry.final_url
    return metadata
