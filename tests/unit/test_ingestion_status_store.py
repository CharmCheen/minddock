"""Unit tests for the ingestion status store."""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from app.stores.ingestion_status_store import (
    IngestionStatusRecord,
    cleanup_stale,
    get_all,
    write_failed,
    write_pending,
    write_ready,
    _STATUS_FILE,
)


class TestIngestionStatusRecord:
    def test_to_dict_round_trip(self) -> None:
        rec = IngestionStatusRecord(
            doc_id="abc123",
            requested_url="https://example.com",
            source_type="url",
            status="indexing",
            error_message=None,
        )
        restored = IngestionStatusRecord.from_dict(rec.to_dict())
        assert restored.doc_id == rec.doc_id
        assert restored.requested_url == rec.requested_url
        assert restored.source_type == rec.source_type
        assert restored.status == rec.status
        assert restored.error_message == rec.error_message

    def test_from_dict_defaults(self) -> None:
        d = {"doc_id": "x", "requested_url": "https://x.com"}
        rec = IngestionStatusRecord.from_dict(d)
        assert rec.status == "indexing"
        assert rec.source_type == "url"
        assert rec.error_message is None


class TestWriteAndRead:
    def test_write_pending_then_get_all(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="doc1", requested_url="https://example.com/1", source_type="url")
        records = get_all()
        assert len(records) == 1
        assert records[0].doc_id == "doc1"
        assert records[0].status == "indexing"

    def test_write_pending_idempotent_same_doc_id(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="doc1", requested_url="https://example.com/1")
        write_pending(doc_id="doc1", requested_url="https://example.com/2")
        records = get_all()
        assert len(records) == 1
        assert records[0].requested_url == "https://example.com/2"

    def test_write_ready_removes_record(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="doc1", requested_url="https://example.com/1")
        write_ready(doc_id="doc1")
        assert get_all() == []

    def test_write_failed_updates_status(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="doc1", requested_url="https://example.com/1")
        write_failed(doc_id="doc1", error_message="fetch error: 404")
        records = get_all()
        assert len(records) == 1
        assert records[0].status == "failed"
        assert records[0].error_message == "fetch error: 404"

    def test_write_failed_non_existent_is_noop(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_failed(doc_id="nonexistent", error_message="should not crash")
        assert get_all() == []

    def test_mixed_records(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="doc1", requested_url="https://a.com/1")
        write_pending(doc_id="doc2", requested_url="https://b.com/2")
        write_failed(doc_id="doc1", error_message="oops")
        write_ready(doc_id="doc2")
        records = {r.doc_id: r for r in get_all()}
        assert "doc1" in records
        assert records["doc1"].status == "failed"
        assert "doc2" not in records


class TestCleanupStale:
    def test_cleanup_removes_old_indexing_records(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        # Manually inject a record with an old timestamp
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        rec = IngestionStatusRecord(
            doc_id="old-doc",
            requested_url="https://old.com",
            status="indexing",
            started_at=old_time,
            updated_at=old_time,
        )
        _write_raw(tmp_path / "status.json", [rec.to_dict()])

        removed = cleanup_stale(max_age_hours=24)
        assert removed == 1
        assert get_all() == []

    def test_cleanup_keeps_recent_indexing_records(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="recent", requested_url="https://recent.com")
        removed = cleanup_stale(max_age_hours=24)
        assert removed == 0
        assert len(get_all()) == 1

    def test_cleanup_keeps_failed_records(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("app.stores.ingestion_status_store._STATUS_FILE", tmp_path / "status.json")
        write_pending(doc_id="stale-failed", requested_url="https://fail.com")
        # Manually set to failed with old timestamp
        records = get_all()
        records[0].status = "failed"
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        records[0].started_at = old_time
        records[0].updated_at = old_time
        _write_raw(tmp_path / "status.json", [r.to_dict() for r in records])

        removed = cleanup_stale(max_age_hours=24)
        assert removed == 0  # failed records are not cleaning up
        assert len(get_all()) == 1


def _write_raw(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
