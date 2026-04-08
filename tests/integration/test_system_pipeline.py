from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from app.llm.mock import MockLLM
from app.rag.retrieval_models import ComparedPoint, EvidenceObject, GroundedCompareResult, RetrievedChunk, RetrievalFilters, SupportStatus
from app.services.compare_service import CompareService
from app.rag.source_models import CatalogQuery, ReplaceDocumentResult, SourceChunkPage, SourceChunkPreview, SourceDetail, SourceInspectResult
from app.rag.url_loader import URLContent
from app.runtime import RuntimeRequest, RuntimeResponse
from app.services.catalog_service import CatalogService
from app.services.chat_service import ChatService
from app.services.grounded_generation import build_context
from app.services.ingest_service import IngestService
from app.services.search_service import SearchService
from app.services.service_models import RetrievalPreparationResult
from app.services.summarize_service import SummarizeService


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text.split()))] for text in texts]


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}

    def replace_document(
        self,
        *,
        doc_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> ReplaceDocumentResult:
        stale_ids = [
            key
            for key, value in self.records.items()
            if value["metadata"]["doc_id"] == doc_id and key not in ids
        ]
        for key in stale_ids:
            del self.records[key]

        for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings, strict=True):
            self.records[item_id] = {
                "document": document,
                "metadata": metadata,
                "embedding": embedding,
            }
        return ReplaceDocumentResult(upserted=len(ids), deleted=len(stale_ids))

    def search_by_text(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        tokens = set(query.lower().split())
        hits: list[tuple[int, RetrievedChunk]] = []

        for item in self.records.values():
            metadata = item["metadata"]
            if filters and not filters.matches_metadata(metadata):
                continue
            text = str(item["document"])
            score = sum(1 for token in tokens if token in text.lower())
            if score <= 0 and tokens:
                continue
            hits.append(
                (
                    score,
                    RetrievedChunk.from_raw(text, metadata, 0.0 if score > 0 else 1.0),
                )
            )

        hits.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in hits[:top_k]]

    def delete_document(self, doc_id: str) -> int:
        ids = [key for key, value in self.records.items() if value["metadata"]["doc_id"] == doc_id]
        for key in ids:
            del self.records[key]
        return len(ids)

    def list_source_details(self, query: CatalogQuery | None = None) -> list[SourceDetail]:
        from app.rag.vectorstore import _build_source_detail

        grouped: dict[str, list[dict[str, object]]] = {}
        for item in self.records.values():
            metadata = dict(item["metadata"])
            if query and query.source_type and metadata.get("source_type") != query.source_type:
                continue
            grouped.setdefault(str(metadata["doc_id"]), []).append(metadata)
        details = [_build_source_detail(rows) for rows in grouped.values()]
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
        rows: list[dict[str, object]] = []
        for item in self.records.values():
            metadata = dict(item["metadata"])
            if metadata.get("doc_id") != doc_id:
                continue
            rows.append({"metadata": metadata, "document": str(item["document"])})
        if not rows:
            return None

        from app.rag.vectorstore import _build_chunk_preview, _build_source_admin_metadata, _build_source_detail, _chunk_sort_key

        rows.sort(key=_chunk_sort_key)
        detail = _build_source_detail([row["metadata"] for row in rows])
        page_rows = rows[offset : offset + limit]
        previews = [
            _build_chunk_preview(row, include_admin_metadata=include_admin_metadata)
            for row in page_rows
        ]
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
            admin_metadata=_build_source_admin_metadata(detail) if include_admin_metadata else {},
        )


@dataclass
class OverrideRuntime:
    runtime_name: str = "override-runtime"
    provider_name: str = "override-provider"

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        assert request.llm_override is not None
        return RuntimeResponse(
            text=request.llm_override.generate(query=request.fallback_query, evidence=request.fallback_evidence),
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


class NoOpReranker:
    def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        return hits


class NoOpCompressor:
    def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        return hits


def build_settings(tmp_path: Path):
    return SimpleNamespace(
        kb_dir=str(tmp_path / "knowledge_base"),
        chroma_dir=str(tmp_path / "data" / "chroma"),
        embedding_model="fake-embedding",
        rebuild_max_retries=1,
        rebuild_retry_seconds=0.0,
    )


def test_end_to_end_local_ingest_search_chat_and_summarize(tmp_path: Path, monkeypatch) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    (kb_dir / "notes.md").write_text("# Storage\nMindDock stores chunks in local Chroma.\n", encoding="utf-8")

    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)
    result = ingest_service.ingest(urls=[])

    assert result.documents == 1
    assert result.chunks == 1
    assert result.failed_sources == []

    search_service = SearchService(vectorstore=store)
    filters = RetrievalFilters(sources=("notes.md",), section="Storage", source_types=("file",))
    search = search_service.search(query="local Chroma", top_k=3, filters=filters)

    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=search_service.retrieve(kwargs["query"], kwargs["top_k"], kwargs["filters"]),
            grounded_hits=search_service.retrieve(kwargs["query"], kwargs["top_k"], kwargs["filters"]),
            context=build_context(search_service.retrieve(kwargs["query"], kwargs["top_k"], kwargs["filters"])),
            citations=[],
        ),
    )

    runtime = OverrideRuntime()
    chat_service = ChatService(
        search_service=search_service,
        reranker=NoOpReranker(),
        compressor=NoOpCompressor(),
        runtime=runtime,
        llm=MockLLM(),
    )
    summarize_service = SummarizeService(
        search_service=search_service,
        reranker=NoOpReranker(),
        compressor=NoOpCompressor(),
        runtime=runtime,
        llm=MockLLM(),
    )

    chat = chat_service.chat(query="local Chroma storage", top_k=3, filters=filters)
    summary = summarize_service.summarize(topic="local Chroma storage", top_k=3, filters=filters)

    assert search.to_api_dict()["hits"][0]["source"] == "notes.md"
    assert chat.metadata.retrieved_count == 1
    assert chat.citations[0].source == "notes.md"
    assert summary.metadata.retrieved_count == 1
    assert summary.citations[0].section == "Storage"


def test_url_ingest_can_be_retrieved_with_url_filter(tmp_path: Path, monkeypatch) -> None:
    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)
    url = "https://example.com/articles/vector-store"

    monkeypatch.setattr(
        "app.rag.source_loader.fetch_url_content",
        lambda _: URLContent(
            requested_url=url,
            final_url=url,
            title="Vector Store Article",
            text="Vector stores persist embeddings and searchable chunks for retrieval augmented generation.",
            status_code=200,
            fetched_at="2026-04-03T00:00:00+00:00",
            ssl_verified=True,
        ),
    )

    result = ingest_service.ingest(urls=[url])
    search_service = SearchService(vectorstore=store)
    hits = search_service.search(
        query="embeddings retrieval",
        top_k=3,
        filters=RetrievalFilters(sources=(url,), source_types=("url",)),
    )

    assert result.documents == 1
    assert result.failed_sources == []
    assert hits.to_api_dict()["hits"][0]["source"] == url
    assert hits.to_api_dict()["hits"][0]["citation"]["source"] == url


def test_repeat_ingest_replaces_stale_chunks_without_rebuild(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    doc_path = kb_dir / "notes.md"
    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)

    doc_path.write_text("# Storage\nOld chunk.\n\n# Search\nAnother old chunk.\n", encoding="utf-8")
    first = ingest_service.ingest()
    assert first.chunks == 2

    doc_path.write_text("# Storage\nOnly new chunk remains.\n", encoding="utf-8")
    second = ingest_service.ingest()
    search_service = SearchService(vectorstore=store)
    hits = search_service.search(
        query="new chunk",
        top_k=5,
        filters=RetrievalFilters(sources=("notes.md",), source_types=("file",)),
    )

    assert second.chunks == 1
    assert len(hits.to_api_dict()["hits"]) == 1
    assert hits.to_api_dict()["hits"][0]["text"] == "Only new chunk remains."


def test_local_file_still_succeeds_when_url_source_fails(tmp_path: Path, monkeypatch) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    (kb_dir / "notes.md").write_text("# Storage\nMindDock stores chunks in local Chroma.\n", encoding="utf-8")

    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)

    monkeypatch.setattr(
        "app.rag.source_loader.fetch_url_content",
        lambda _: (_ for _ in ()).throw(RuntimeError("network failed")),
    )

    result = ingest_service.ingest(urls=["https://example.com/fail"])

    assert result.documents == 1
    assert len(result.failed_sources) == 1
    assert result.failed_sources[0].source_type == "url"


def test_multi_value_filters_work_for_file_and_url_sources(tmp_path: Path, monkeypatch) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    (kb_dir / "storage.md").write_text("# Storage\nMindDock stores chunks in local Chroma.\n", encoding="utf-8")

    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)
    monkeypatch.setattr(
        "app.rag.source_loader.fetch_url_content",
        lambda _: URLContent(
            requested_url="https://example.com/requested",
            final_url="https://example.com/final",
            title="Example Storage",
            text="Example domain stores reference content for retrieval filtering.",
            status_code=200,
            fetched_at="2026-04-03T00:00:00+00:00",
            ssl_verified=True,
        ),
    )

    ingest_service.ingest(urls=["https://example.com/requested"])
    search_service = SearchService(vectorstore=store)
    result = search_service.search(
        query="storage Chroma retrieval",
        top_k=5,
        filters=RetrievalFilters(
            sources=("storage.md", "https://example.com/final"),
            source_types=("file", "url"),
            title_contains="storage",
        ),
    )
    url_only = search_service.search(
        query="reference retrieval",
        top_k=5,
        filters=RetrievalFilters(
            source_types=("url",),
            requested_url_contains="requested",
        ),
    )

    assert len(result.to_api_dict()["hits"]) == 2
    assert len(url_only.to_api_dict()["hits"]) == 1
    assert url_only.to_api_dict()["hits"][0]["source"] == "https://example.com/final"


def test_catalog_delete_and_reingest_lifecycle(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    (kb_dir / "notes.md").write_text("# Storage\nMindDock stores chunks in local Chroma.\n", encoding="utf-8")

    store = InMemoryVectorStore()
    settings = build_settings(tmp_path)
    ingest_service = IngestService(settings=settings, embedder=FakeEmbedder(), collection=store)
    catalog_service = CatalogService(settings=settings, collection=store, ingest_service=ingest_service)

    ingest_service.ingest()
    listing = catalog_service.list_sources()
    detail = catalog_service.get_source_detail(source="notes.md")
    inspect = catalog_service.inspect_source(source="notes.md", limit=1, offset=0, include_admin_metadata=True)
    deleted = catalog_service.delete_source(source="notes.md")
    listing_after_delete = catalog_service.list_sources()
    reingested = catalog_service.reingest_source(source="notes.md")
    listing_after_reingest = catalog_service.list_sources()

    assert listing.entries[0].source == "notes.md"
    assert detail.found is True and detail.detail is not None
    assert inspect.found is True and inspect.inspect is not None
    assert inspect.inspect.chunk_page.returned_chunks == 1
    assert inspect.inspect.chunk_page.chunks[0].preview_text.startswith("MindDock stores")
    assert deleted.result.deleted_chunks == 1
    assert listing_after_delete.metadata.empty_result is True
    assert reingested.found is True
    assert reingested.source_result is not None and reingested.source_result.ok is True
    assert listing_after_reingest.entries[0].source == "notes.md"


def test_end_to_end_local_ingest_and_compare_happy_path(tmp_path: Path) -> None:
    """E2E: ingest two docs -> compare returns grounded common_points and differences."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    (kb_dir / "doc_a.md").write_text(
        "# Storage\nMindDock uses Chroma for vector storage.\n", encoding="utf-8"
    )
    (kb_dir / "doc_b.md").write_text(
        "# Storage\nMindDock uses PostgreSQL for structured storage.\n", encoding="utf-8"
    )

    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)
    result = ingest_service.ingest(urls=[])

    assert result.documents == 2
    assert result.chunks == 2
    assert result.failed_sources == []

    search_service = SearchService(vectorstore=store)
    compare_service = CompareService(
        search_service=search_service,
        reranker=NoOpReranker(),
        compressor=NoOpCompressor(),
    )

    filters = RetrievalFilters(sources=("doc_a.md", "doc_b.md"), source_types=("file",))
    compare_result = compare_service.compare(
        question="Compare the storage approaches in doc_a.md and doc_b.md",
        top_k=4,
        filters=filters,
    )

    assert compare_result.compare_result.support_status == SupportStatus.SUPPORTED
    assert len(compare_result.compare_result.common_points) >= 1
    assert compare_result.citations


def test_end_to_end_local_ingest_and_compare_insufficient_evidence(tmp_path: Path) -> None:
    """E2E: ingest one doc -> compare returns insufficient_evidence when < 2 groups."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    (kb_dir / "only_doc.md").write_text(
        "# Storage\nMindDock uses Chroma for vector storage.\n", encoding="utf-8"
    )

    store = InMemoryVectorStore()
    ingest_service = IngestService(settings=build_settings(tmp_path), embedder=FakeEmbedder(), collection=store)
    result = ingest_service.ingest(urls=[])

    assert result.documents == 1

    search_service = SearchService(vectorstore=store)
    compare_service = CompareService(
        search_service=search_service,
        reranker=NoOpReranker(),
        compressor=NoOpCompressor(),
    )

    filters = RetrievalFilters(sources=("only_doc.md",), source_types=("file",))
    compare_result = compare_service.compare(
        question="Compare storage approaches across documents",
        top_k=4,
        filters=filters,
    )

    assert compare_result.compare_result.support_status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert compare_result.metadata.insufficient_evidence is True
