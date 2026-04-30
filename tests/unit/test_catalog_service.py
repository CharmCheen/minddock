"""Unit tests for source catalog and lifecycle services."""

import pytest
from pathlib import Path
from types import SimpleNamespace

from app.rag.source_models import CatalogQuery, SourceCatalogEntry, SourceChunkPage, SourceChunkPreview, SourceDetail, SourceDescriptor, SourceInspectResult, SourceState
from app.services.catalog_service import CatalogService


@pytest.fixture(autouse=True)
def _isolate_status_store(monkeypatch):
    """Prevent status-store file entries from leaking into unit tests.

    Integration tests write failed/pending records to the real JSON store.
    Unit tests use FakeCollection and don't need those entries; this patch
    ensures they always see an empty status store.
    """
    monkeypatch.setattr("app.services.catalog_service.get_all", lambda: [])
    monkeypatch.setattr("app.services.catalog_service.write_ready", lambda doc_id: None)


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


def test_list_sources_merges_pending_status_records(monkeypatch, tmp_path: Path) -> None:
    """Extra entries from the status store must appear alongside Chroma entries."""
    from unittest.mock import patch
    from app.stores.ingestion_status_store import IngestionStatusRecord

    pending_records = [
        IngestionStatusRecord(doc_id="pending-url", requested_url="https://pending.com", source_type="url", status="indexing"),
        IngestionStatusRecord(doc_id="failed-url", requested_url="https://failed.com", source_type="url", status="failed", error_message="DNS error"),
    ]

    def fake_get_all():
        return pending_records

    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )
    with patch("app.services.catalog_service.get_all", fake_get_all):
        result = service.list_sources()

    doc_ids = {e.doc_id for e in result.entries}
    # Both Chroma entries and status-store entries are present
    assert "d-file" in doc_ids
    assert "d-url" in doc_ids
    assert "pending-url" in doc_ids
    assert "failed-url" in doc_ids

    # Check failed entry carries error_message and correct status
    failed_entry = next(e for e in result.entries if e.doc_id == "failed-url")
    assert failed_entry.state is not None
    assert failed_entry.state.ingest_status == "failed"
    assert failed_entry.state.error_message == "DNS error"
    assert failed_entry.chunk_count == 0

    # pending entry
    pending_entry = next(e for e in result.entries if e.doc_id == "pending-url")
    assert pending_entry.state is not None
    assert pending_entry.state.ingest_status == "indexing"
    assert pending_entry.chunk_count == 0


def test_list_sources_respects_source_type_filter_for_pending(monkeypatch, tmp_path: Path) -> None:
    """Pending entries must be filtered by source_type just like Chroma entries."""
    from unittest.mock import patch
    from app.stores.ingestion_status_store import IngestionStatusRecord

    pending_records = [
        IngestionStatusRecord(doc_id="pending-url", requested_url="https://pending.com", source_type="url", status="indexing"),
        IngestionStatusRecord(doc_id="pending-file", requested_url="notes.txt", source_type="file", status="indexing"),
    ]

    def fake_get_all():
        return pending_records

    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )
    with patch("app.services.catalog_service.get_all", fake_get_all):
        url_result = service.list_sources(source_type="url")
        file_result = service.list_sources(source_type="file")

    assert all(e.source_type == "url" for e in url_result.entries)
    assert all(e.source_type == "file" for e in file_result.entries)
    # pending-url only in url result, pending-file only in file result
    url_doc_ids = {e.doc_id for e in url_result.entries}
    file_doc_ids = {e.doc_id for e in file_result.entries}
    assert "pending-url" in url_doc_ids
    assert "pending-url" not in file_doc_ids
    assert "pending-file" in file_doc_ids
    assert "pending-file" not in url_doc_ids


def test_list_sources_deduplicates_chroma_over_status(monkeypatch, tmp_path: Path) -> None:
    """When the same doc_id is in both Chroma and status store, Chroma wins."""
    from unittest.mock import patch
    from app.stores.ingestion_status_store import IngestionStatusRecord

    # d-url is already in FakeCollection (chroma) with ingest_status=ready
    # A status-store record for the same doc_id should be ignored
    pending_records = [
        IngestionStatusRecord(doc_id="d-url", requested_url="https://stale.com", source_type="url", status="indexing"),
    ]

    def fake_get_all():
        return pending_records

    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )
    with patch("app.services.catalog_service.get_all", fake_get_all):
        result = service.list_sources()

    # Should have exactly 2 entries (d-file + d-url from Chroma)
    assert len(result.entries) == 2
    d_url_entry = next(e for e in result.entries if e.doc_id == "d-url")
    # Chroma's real entry wins, not the indexing placeholder
    assert d_url_entry.state is not None and d_url_entry.state.ingest_status == "ready"


def test_list_sources_deduplicates_status_records_by_url_identity(monkeypatch, tmp_path: Path) -> None:
    """Ready Chroma URL entries should suppress stale requested/final URL status rows."""
    from unittest.mock import patch
    from app.stores.ingestion_status_store import IngestionStatusRecord

    pending_records = [
        IngestionStatusRecord(
            doc_id="stale-requested-doc",
            requested_url="https://example.com/requested/",
            source_type="url",
            status="indexing",
        ),
        IngestionStatusRecord(
            doc_id="stale-final-doc",
            requested_url="https://example.com/final/",
            source_type="url",
            status="failed",
            error_message="old redirect failure",
        ),
    ]

    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )
    with patch("app.services.catalog_service.get_all", lambda: pending_records):
        result = service.list_sources()

    doc_ids = {e.doc_id for e in result.entries}
    assert doc_ids == {"d-file", "d-url"}
    assert next(e for e in result.entries if e.doc_id == "d-url").source == "https://example.com/final"


def test_list_sources_does_not_dedupe_distinct_urls_on_same_domain(monkeypatch, tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.stores.ingestion_status_store import IngestionStatusRecord

    pending_records = [
        IngestionStatusRecord(
            doc_id="different-url-doc",
            requested_url="https://example.com/different",
            source_type="url",
            status="indexing",
        ),
    ]
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )

    with patch("app.services.catalog_service.get_all", lambda: pending_records):
        result = service.list_sources()

    doc_ids = {e.doc_id for e in result.entries}
    assert "d-url" in doc_ids
    assert "different-url-doc" in doc_ids


def test_catalog_service_resolves_status_only_failed_source(monkeypatch, tmp_path: Path) -> None:
    from app.stores.ingestion_status_store import IngestionStatusRecord

    failed_record = IngestionStatusRecord(
        doc_id="failed-doc",
        requested_url="https://failed.example/article",
        source_type="url",
        status="failed",
        error_message="HTTP 500",
    )
    cleared_doc_ids: list[str] = []
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=FakeIngestService(),
    )

    monkeypatch.setattr("app.services.catalog_service.get_all", lambda: [failed_record])
    monkeypatch.setattr("app.services.catalog_service.write_ready", lambda doc_id: cleared_doc_ids.append(doc_id))

    detail = service.get_source_detail(doc_id="failed-doc")
    delete = service.delete_source(source="https://failed.example/article")
    reingest = service.reingest_source(doc_id="failed-doc")

    assert detail.found is True
    assert detail.detail is not None
    assert detail.detail.entry.chunk_count == 0
    assert detail.detail.entry.state is not None
    assert detail.detail.entry.state.ingest_status == "failed"
    assert detail.detail.entry.state.error_message == "HTTP 500"
    assert delete.result.found is True
    assert delete.result.deleted_chunks == 0
    assert cleared_doc_ids == ["failed-doc"]
    assert reingest.found is True
    assert reingest.source_result is not None
    assert reingest.source_result.descriptor.source == "https://failed.example/article"


def test_catalog_service_reingests_status_only_pending_url_without_noop(monkeypatch, tmp_path: Path) -> None:
    from app.stores.ingestion_status_store import IngestionStatusRecord

    pending_record = IngestionStatusRecord(
        doc_id="pending-doc",
        requested_url="https://pending.example/article",
        source_type="url",
        status="indexing",
    )
    ingest_service = FakeIngestService()
    service = CatalogService(
        settings=SimpleNamespace(kb_dir=str(tmp_path / "kb")),
        collection=FakeCollection(),
        ingest_service=ingest_service,
    )
    monkeypatch.setattr("app.services.catalog_service.get_all", lambda: [pending_record])

    reingest = service.reingest_source(doc_id="pending-doc")

    assert reingest.found is True
    assert reingest.source_result is not None
    assert reingest.source_result.descriptor.source == "https://pending.example/article"
    assert ingest_service.last_descriptor is not None
    assert ingest_service.last_descriptor.source == "https://pending.example/article"
