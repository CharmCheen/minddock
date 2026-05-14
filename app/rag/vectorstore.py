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


def _notify_bm25_invalidation() -> None:
    try:
        from app.rag.hybrid_retrieval import _notify_invalidation

        _notify_invalidation()
    except ImportError:
        pass


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

    def health_check(self) -> bool:
        """Check if the ChromaDB collection is accessible."""
        try:
            self._store._collection.count()
            return True
        except Exception:
            return False

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
        _notify_bm25_invalidation()

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

    def get_chunks_by_ids(
        self,
        chunk_ids: list[str],
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        """Return complete chunks for ids, preserving the requested id order."""

        ordered_ids = [chunk_id for chunk_id in dict.fromkeys(chunk_ids) if chunk_id]
        if not ordered_ids:
            return []

        result = self._store._collection.get(ids=ordered_ids, include=["documents", "metadatas"])
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        by_id: dict[str, RetrievedChunk] = {}
        for chunk_id, document, metadata in zip(ids, documents, metadatas, strict=True):
            metadata = dict(metadata or {})
            by_id[str(chunk_id)] = RetrievedChunk.from_raw(str(document or ""), metadata, None)

        hits = [by_id[chunk_id] for chunk_id in ordered_ids if chunk_id in by_id]
        return _apply_post_filters(hits, filters)

    def delete_ids(self, ids: list[str]) -> int:
        if not ids:
            return 0
        self._store.delete(ids=ids)
        _notify_bm25_invalidation()
        return len(ids)

    def replace_document(
        self,
        *,
        doc_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]] | None = None,
        allow_empty_replace: bool = False,
    ) -> ReplaceDocumentResult:
        existing_ids = set(self.list_document_chunk_ids(doc_id))
        new_ids = set(ids)

        if not ids and existing_ids and not allow_empty_replace:
            raise ValueError(
                f"Refusing empty replacement for indexed document `{doc_id}`; "
                "use allow_empty_replace=True for explicit deletes."
            )

        if ids:
            self.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

        deleted = self.delete_ids(sorted(existing_ids - new_ids))

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
        for index, text in enumerate(documents[0]):
            metadata = metadatas[0][index] or {}
            distance = distances[0][index] if distances and distances[0] else None
            hits.append(RetrievedChunk.from_raw(text, metadata, distance))

        return _apply_post_filters(hits, filters)[:top_k]

    def delete_document(self, doc_id: str) -> int:
        result = self._store.get(where={"doc_id": doc_id}, include=[])
        ids = result.get("ids") or []
        if not ids:
            return 0

        self._store.delete(where={"doc_id": doc_id})
        _notify_bm25_invalidation()
        return len(ids)

    def count_document_chunks(self, doc_id: str) -> int:
        result = self._store.get(where={"doc_id": doc_id}, include=[])
        ids = result.get("ids") or []
        return len(ids)

    def get_document_chunks(
        self,
        doc_id: str,
        *,
        include_text: bool = True,
    ) -> list[dict[str, str]]:
        """Return all chunks for a document as dicts with chunk_id, text, metadata.

        This is a public read-only accessor for services that need raw chunk
        text and metadata without going through the retrieval pipeline.
        """
        include_fields = ["metadatas"]
        if include_text:
            include_fields.append("documents")
        result = self._store.get(where={"doc_id": doc_id}, include=include_fields)
        ids = result.get("ids") or []
        documents = result.get("documents") or [] if include_text else []
        metadatas = result.get("metadatas") or []

        rows: list[dict[str, str]] = []
        for i, chunk_id in enumerate(ids):
            meta = dict(metadatas[i] or {}) if i < len(metadatas) else {}
            text = str(documents[i] or "") if include_text and i < len(documents) else ""
            rows.append({
                "chunk_id": str(chunk_id),
                "doc_id": doc_id,
                "source": str(meta.get("source", "")),
                "text": text,
                **{k: str(v) for k, v in meta.items() if k not in ("source",)},
            })
        return rows

    def get_neighbor_chunks(
        self,
        hit: RetrievedChunk,
        *,
        before: int,
        after: int,
    ) -> list[RetrievedChunk]:
        """Return chunks from the same document around a retrieved hit.

        This is a read-only helper for answer/citation evidence windows. It
        prefers structured PDF ``order_in_doc`` metadata and falls back to the
        numeric suffix in ``chunk_id`` for older/non-PDF chunks.
        """

        if not hit.doc_id:
            return [hit]

        center_order = _chunk_order_value_from_hit(hit)
        if center_order is None:
            return [hit]

        result = self._store.get(where={"doc_id": hit.doc_id}, include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        if not metadatas:
            return [hit]

        lower = center_order - max(before, 0)
        upper = center_order + max(after, 0)
        neighbors: list[tuple[int, RetrievedChunk]] = []
        for metadata, document in zip(metadatas, documents, strict=True):
            metadata = dict(metadata or {})
            order = _chunk_order_value_from_metadata(metadata)
            if order is None or order < lower or order > upper:
                continue
            neighbors.append((order, RetrievedChunk.from_raw(str(document or ""), metadata, None)))

        neighbors.sort(key=lambda item: (item[0], item[1].chunk_id))
        chunks = [chunk for _, chunk in neighbors]
        return chunks or [hit]

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
        detail = _build_source_detail(
            [row["metadata"] for row in rows],
            row_documents=[row["document"] for row in rows],
        )
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


def health_check_vectorstore() -> bool:
    """Check if the vectorstore is accessible. Returns True if ready, False otherwise."""
    try:
        store = get_vectorstore()
        return store.health_check()
    except Exception:
        return False


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


def get_neighbor_chunks(
    hit: RetrievedChunk,
    *,
    before: int,
    after: int,
) -> list[RetrievedChunk]:
    """Return same-document neighbors around a retrieved hit."""

    return get_vectorstore().get_neighbor_chunks(hit, before=before, after=after)


def replace_document(
    *,
    doc_id: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, str]],
    embeddings: list[list[float]] | None = None,
    allow_empty_replace: bool = False,
) -> ReplaceDocumentResult:
    """Upsert a document's current chunks and delete stale chunk ids."""

    return get_vectorstore().replace_document(
        doc_id=doc_id,
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
        allow_empty_replace=allow_empty_replace,
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


def _build_source_detail(
    rows: list[dict[str, object]],
    row_documents: list[str] | None = None,
) -> SourceDetail:
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

    # Ensure media transcript metadata appears in representative_metadata
    # even when Chroma get returns sparse results for the first row.
    _MEDIA_METADATA_KEYS = (
        "source_media", "source_kind", "loader_name",
        "transcript_provider", "transcript_status", "transcript_error",
        "media_filename", "retrieval_basis",
    )
    for row in rows:
        loader = str(row.get("loader_name", ""))
        for key in _MEDIA_METADATA_KEYS:
            if key not in representative_metadata and key in row:
                representative_metadata[key] = row[key]
        if loader in ("audio.transcribe", "video.transcribe"):
            break

    # Aggregate derived chunk flags and previews for source-level display
    derived_kinds: set[str] = set()
    for idx, row in enumerate(rows):
        if str(row.get("is_derived") or "").strip().lower() != "true":
            continue
        kind = str(row.get("derived_kind") or "").strip()
        if not kind:
            continue
        derived_kinds.add(kind)
        if row_documents and idx < len(row_documents):
            text = row_documents[idx]
        else:
            text = ""
        if kind == "media_summary" and "derived_summary_preview" not in representative_metadata and text:
            representative_metadata["derived_summary_preview"] = text[:1000]
        elif kind == "media_outline" and "derived_outline_preview" not in representative_metadata and text:
            representative_metadata["derived_outline_preview"] = text[:800]
    if "media_summary" in derived_kinds:
        representative_metadata["has_derived_summary"] = "true"
    if "media_outline" in derived_kinds:
        representative_metadata["has_derived_outline"] = "true"

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
    chunk_order = _chunk_order_value_from_metadata(metadata)
    return (chunk_order if chunk_order is not None else 10**9, chunk_id)


def _chunk_order_value_from_hit(hit: RetrievedChunk) -> int | None:
    order = _parse_int(hit.extra_metadata.get("order_in_doc"))
    if order is not None:
        return order
    return _extract_chunk_index(hit.chunk_id)


def _chunk_order_value_from_metadata(metadata: dict[str, object]) -> int | None:
    order = _parse_int(metadata.get("order_in_doc"))
    if order is not None:
        return order
    return _extract_chunk_index(str(metadata.get("chunk_id") or ""))


def _parse_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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

    # Expose derived chunk metadata for frontend display
    is_derived = str(metadata.get("is_derived") or "").strip().lower()
    if is_derived == "true":
        admin_metadata["is_derived"] = "true"
        derived_kind = str(metadata.get("derived_kind") or "").strip()
        if derived_kind:
            admin_metadata["derived_kind"] = derived_kind
        derived_from = str(metadata.get("derived_from") or "").strip()
        if derived_from:
            admin_metadata["derived_from"] = derived_from
        derived_basis = str(metadata.get("derived_basis") or "").strip()
        if derived_basis:
            admin_metadata["derived_basis"] = derived_basis
        evidence_basis = str(metadata.get("evidence_basis") or "").strip()
        if evidence_basis:
            admin_metadata["evidence_basis"] = evidence_basis

    return SourceChunkPreview(
        chunk_id=chunk_id,
        chunk_index=_extract_chunk_index(chunk_id),
        preview_text=_preview_text(str(row.get("document") or "")),
        title=str(metadata.get("title") or ""),
        section=str(metadata.get("section") or "").strip() or None,
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
