"""Thread-safe JSON-backed ingestion status store.

Status records track URL sources that are currently being ingested or have
failed, but are not yet (or never will be) present in Chroma.

File layout:
    data/
        ingestion_status.json   <- one JSON array of IngestionStatusRecord

This store is NOT used for retrieval — only for /sources catalog visibility.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

_STATUS_FILE = Path("data/ingestion_status.json")

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class IngestionStatusRecord:
    """Lightweight status record for a URL source being ingested."""

    __slots__ = ("doc_id", "requested_url", "source_type", "status", "error_message", "started_at", "updated_at")

    def __init__(
        self,
        *,
        doc_id: str,
        requested_url: str,
        source_type: str = "url",
        status: str = "indexing",
        error_message: str | None = None,
        started_at: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        self.doc_id = doc_id
        self.requested_url = requested_url
        self.source_type = source_type
        self.status = status
        self.error_message = error_message
        now = _utc_now_iso()
        self.started_at = started_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "requested_url": self.requested_url,
            "source_type": self.source_type,
            "status": self.status,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IngestionStatusRecord":
        return cls(
            doc_id=d["doc_id"],
            requested_url=d["requested_url"],
            source_type=d.get("source_type", "url"),
            status=d.get("status", "indexing"),
            error_message=d.get("error_message"),
            started_at=d.get("started_at"),
            updated_at=d.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_records() -> list[IngestionStatusRecord]:
    if not _STATUS_FILE.exists():
        return []
    try:
        with open(_STATUS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            return []
        return [IngestionStatusRecord.from_dict(r) for r in data]
    except (json.JSONDecodeError, OSError):
        return []


def _write_records(records: list[IngestionStatusRecord]) -> None:
    _STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATUS_FILE, "w", encoding="utf-8") as fh:
        json.dump([r.to_dict() for r in records], fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_pending(doc_id: str, requested_url: str, source_type: str = "url") -> None:
    """Write or overwrite a pending record before ingestion starts."""
    with _lock:
        records = _read_records()
        # Remove any existing record for this doc_id (stale or failed)
        records = [r for r in records if r.doc_id != doc_id]
        records.append(IngestionStatusRecord(doc_id=doc_id, requested_url=requested_url, source_type=source_type))
        _write_records(records)


def write_ready(doc_id: str) -> None:
    """Remove the record once Chroma has the real data (ingest succeeded)."""
    with _lock:
        records = _read_records()
        records = [r for r in records if r.doc_id != doc_id]
        _write_records(records)


def write_failed(doc_id: str, error_message: str) -> None:
    """Update the record to failed status without removing it."""
    with _lock:
        records = _read_records()
        for r in records:
            if r.doc_id == doc_id:
                r.status = "failed"
                r.error_message = error_message
                r.updated_at = _utc_now_iso()
                break
        else:
            return
        _write_records(records)


def get_all() -> list[IngestionStatusRecord]:
    """Return all current status records."""
    with _lock:
        return _read_records()


def cleanup_stale(max_age_hours: int = 24) -> int:
    """Remove 'indexing' records older than max_age_hours. Returns count removed."""
    with _lock:
        records = _read_records()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        kept: list[IngestionStatusRecord] = []
        removed = 0
        for r in records:
            if r.status == "indexing":
                try:
                    started = datetime.fromisoformat(r.started_at)
                except ValueError:
                    kept.append(r)
                    continue
                if started.replace(tzinfo=timezone.utc) < cutoff:
                    removed += 1
                    continue
            kept.append(r)
        _write_records(kept)
        return removed
