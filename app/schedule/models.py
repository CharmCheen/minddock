"""Schedule candidate domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ScheduleCandidate:
    """One auto-identified schedule candidate from an ingested chunk."""

    id: str
    title: str
    start_date: str | None = None
    start_time: str | None = None
    end_date: str | None = None
    end_time: str | None = None
    date_text: str | None = None
    location: str | None = None
    description: str | None = None
    source_id: str | None = None
    doc_id: str | None = None
    chunk_id: str | None = None
    source: str | None = None
    evidence_text: str | None = None
    confidence: float = 0.0
    status: str = "pending"
    dedup_key: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start_date": self.start_date,
            "start_time": self.start_time,
            "end_date": self.end_date,
            "end_time": self.end_time,
            "date_text": self.date_text,
            "location": self.location,
            "description": self.description,
            "source_id": self.source_id,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "source": self.source,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
            "status": self.status,
            "dedup_key": self.dedup_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleCandidate:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            start_date=data.get("start_date"),
            start_time=data.get("start_time"),
            end_date=data.get("end_date"),
            end_time=data.get("end_time"),
            date_text=data.get("date_text"),
            location=data.get("location"),
            description=data.get("description"),
            source_id=data.get("source_id"),
            doc_id=data.get("doc_id"),
            chunk_id=data.get("chunk_id"),
            source=data.get("source"),
            evidence_text=data.get("evidence_text"),
            confidence=float(data.get("confidence", 0.0)),
            status=str(data.get("status", "pending")),
            dedup_key=str(data.get("dedup_key", "")),
            created_at=str(data.get("created_at", _utc_now_iso())),
            updated_at=str(data.get("updated_at", _utc_now_iso())),
        )
