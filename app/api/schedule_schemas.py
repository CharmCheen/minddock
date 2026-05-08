"""Pydantic schemas for schedule candidate API endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScheduleCandidateItem(BaseModel):
    """One schedule candidate returned by the API."""

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
    created_at: str = ""
    updated_at: str = ""


class ScheduleCandidateListResponse(BaseModel):
    """Response body for listing schedule candidates."""

    items: list[ScheduleCandidateItem]
    total: int


class ScheduleScanRequest(BaseModel):
    """Request body for triggering a schedule scan."""

    doc_id: str | None = Field(default=None, description="Scan only this document. Omit to scan all.")
    source: str | None = Field(default=None, description="Filter by source identifier.")


class ScheduleScanResponse(BaseModel):
    """Response body for a schedule scan."""

    chunks_scanned: int
    candidates_extracted: int
    candidates_added: int
    candidates_skipped: int
    elapsed_ms: float


class ScheduleStatusUpdateResponse(BaseModel):
    """Response body for confirm/dismiss operations."""

    found: bool
    candidate: ScheduleCandidateItem | None = None


class ScheduleSkillRunRequest(BaseModel):
    """Request body for the schedule-extraction skill run endpoint."""

    doc_id: str | None = Field(default=None, description="Scan only this document.")
    source: str | None = Field(default=None, description="Filter by source identifier.")


class ScheduleSkillRunResponse(BaseModel):
    """Response body for the schedule-extraction skill run."""

    success: bool
    skill_id: str = "schedule_extraction"
    scan_result: ScheduleScanResponse
    summary_text: str = ""
