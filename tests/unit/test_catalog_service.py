"""Unit tests for source catalog and lifecycle services."""

from pathlib import Path
from types import SimpleNamespace

from app.rag.source_models import CatalogQuery, SourceCatalogEntry, SourceChunkPage, SourceChunkPreview, SourceDetail, SourceDescriptor, SourceInspectResult, SourceState
from app.services.catalog_service import CatalogService


class FakeCollection:
    def __init__(self) -> None:
        self.deleted_doc_id: str | None = None
        self.details = [
            SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d-file",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                    sections=("Storage",),
                    state=SourceState(
                        doc_id="d-file",
                        source="notes.md",
                        current_version="hash-file",
                        content_hash="hash-file",
                        last_ingested_at="2026-04-05T10:00:00+00:00",
                        chunk_count=2,
                        ingest_status="ready",
                    ),
                ),
                representative_metadata={"title": "notes", "source": "notes.md"},
            ),
            SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d-url",
                    source="https://example.com/final",
                    source_type="url",
                    title="example",
                    chunk_count=1,
                    requested_url="https://example.com/requested",
                    final_url="https://example.com/final",
                    state=SourceState(
                        doc_id="d-url",
                        source="https://example.com/final",
                        current_version="hash-url",
                        content_hash="hash-url",
                        last_ingested_at="2026-04-05T10:01:00+00:00",
                        chunk_count=1,
                        ingest_status="ready",
                    ),
                ),
                representative_metadata={"requested_url": "https://example.com/requested"},
            ),
        ]

    def list_source_details(self, query: CatalogQuery | None = None):
        if query and query.source_type:
            return [item for item in self.details if item.entry.source_type == query.source_type]
        return list(self.details)

    def delete_document(self, doc_id: str) -> int:
        self.deleted_doc_id = doc_id
        return 2 if doc_id == "d-file" else 0

    def inspect_source(
        self,
        doc_id: str,
        *,
        limit: int,
        offset: int,
        include_admin_metadata: bool = False,
    ):
        detail = next((item for item in self.details if item.entry.doc_id == doc_id), None)
        if detail is None:
            return None
        previews = [
            SourceChunkPreview(
                chunk_id=f"{doc_id}:{index}",
                chunk_index=index,
                preview_text=f"chunk preview {index}",
                title=detail.entry.title,
                section="Storage" if index == 0 else None,
                location="Storage" if index == 0 else detail.entry.source,
                ref=f"{detail.entry.title} > chunk {index}",
                admin_metadata={"doc_id": doc_id} if include_admin_metadata else {},
            )
            for index in range(detail.entry.chunk_count)
        ]
        page = previews[offset : offset + limit]
        return SourceInspectResult(
            detail=detail,
            chunk_page=SourceChunkPage(
                total_chunks=len(previews),
                returned_chunks=len(page),
                limit=limit,
                offset=offset,
                chunks=page,
            ),
            include_admin_metadata=include_admin_metadata,
            admin_metadata={"doc_id": doc_id, "chunk_count": detail.entry.chunk_count} if include_admin_metadata else {},
        )


class FakeIngestService:
    def __init__(self) -> None:
        self.last_descriptor: SourceDescriptor | None = None

    def ingest_descriptor(self, descriptor: SourceDescriptor):
        from app.rag.source_models import IngestSourceResult

        self.last_descriptor = descriptor
        return IngestSourceResult(descriptor=descriptor, ok=True, chunks_upserted=3, chunks_deleted=1)


def test_catalog_service_lists_and_filters_sources(tmp_path: Path) -> None:
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )

    result = service.list_sources()
    filtered = service.list_sources(source_type="url")

    assert len(result.entries) == 2
    assert filtered.entries[0].source_type == "url"


def test_catalog_service_returns_detail_delete_and_reingest(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    (kb_dir / "notes.md").write_text("# Storage\ncontent\n", encoding="utf-8")
    collection = FakeCollection()
    ingest_service = FakeIngestService()
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(kb_dir)),
        collection=collection,
        ingest_service=ingest_service,
    )

    detail = service.get_source_detail(doc_id="d-file")
    delete = service.delete_source(source="notes.md")
    reingest = service.reingest_source(doc_id="d-file")

    assert detail.found is True
    assert detail.detail is not None and detail.detail.entry.source == "notes.md"
    assert detail.detail.entry.state is not None
    assert detail.detail.entry.state.current_version == "hash-file"
    assert delete.result.deleted_chunks == 2
    assert collection.deleted_doc_id == "d-file"
    assert reingest.found is True
    assert reingest.source_result is not None and reingest.source_result.chunks_upserted == 3
    assert ingest_service.last_descriptor is not None and ingest_service.last_descriptor.source == "notes.md"


def test_catalog_service_handles_missing_source(tmp_path: Path) -> None:
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )

    detail = service.get_source_detail(doc_id="missing")
    delete = service.delete_source(doc_id="missing")
    reingest = service.reingest_source(source="missing")

    assert detail.found is False
    assert delete.result.found is False
    assert reingest.found is True
    assert reingest.source_result is not None and reingest.source_result.descriptor.source == "missing"


def test_catalog_service_inspects_chunk_page_with_admin_metadata(tmp_path: Path) -> None:
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )

    result = service.inspect_source(doc_id="d-file", limit=1, offset=1, include_admin_metadata=True)

    assert result.found is True
    assert result.inspect is not None
    assert result.inspect.chunk_page.total_chunks == 2
    assert result.inspect.chunk_page.returned_chunks == 1
    assert result.inspect.chunk_page.chunks[0].chunk_index == 1
    assert result.inspect.admin_metadata["chunk_count"] == 2
    assert result.inspect.chunk_page.chunks[0].admin_metadata["doc_id"] == "d-file"


def test_catalog_service_normalizes_invalid_paging_for_inspect(tmp_path: Path) -> None:
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )

    result = service.inspect_source(doc_id="d-file", limit=0, offset=-5)

    assert result.found is True
    assert result.inspect is not None
    assert result.inspect.chunk_page.limit == 1
    assert result.inspect.chunk_page.offset == 0
    assert "normalized" in result.metadata.warnings[0]
