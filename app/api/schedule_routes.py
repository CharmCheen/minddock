"""HTTP routes for schedule candidate management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.api.schedule_schemas import (
    ScheduleCandidateItem,
    ScheduleCandidateListResponse,
    ScheduleScanRequest,
    ScheduleScanResponse,
    ScheduleSkillRunRequest,
    ScheduleSkillRunResponse,
    ScheduleStatusUpdateResponse,
)
from app.schedule.models import ScheduleCandidate
from app.services.schedule_candidate_service import ScheduleCandidateService
from app.services.schedule_ics_service import build_ics_calendar

logger = logging.getLogger(__name__)

router = APIRouter()

_service = ScheduleCandidateService()

_VALID_STATUSES = frozenset({"pending", "confirmed", "dismissed"})


def _to_item(c: ScheduleCandidate) -> ScheduleCandidateItem:
    return ScheduleCandidateItem(
        id=c.id,
        title=c.title,
        start_date=c.start_date,
        start_time=c.start_time,
        end_date=c.end_date,
        end_time=c.end_time,
        date_text=c.date_text,
        location=c.location,
        description=c.description,
        source_id=c.source_id,
        doc_id=c.doc_id,
        chunk_id=c.chunk_id,
        source=c.source,
        evidence_text=c.evidence_text,
        confidence=c.confidence,
        status=c.status,
        dedup_key=c.dedup_key,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get(
    "/frontend/schedule-candidates",
    response_model=ScheduleCandidateListResponse,
    summary="List schedule candidates",
)
def list_schedule_candidates(
    status: str | None = Query(default=None, description="Filter by status: pending, confirmed, dismissed"),
) -> ScheduleCandidateListResponse:
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: pending, confirmed, dismissed",
        )
    logger.debug("Schedule candidate list endpoint called: status=%s", status)
    candidates = _service.list_candidates(status=status)
    return ScheduleCandidateListResponse(
        items=[_to_item(c) for c in candidates],
        total=len(candidates),
    )


@router.post(
    "/frontend/schedule-candidates/scan",
    response_model=ScheduleScanResponse,
    summary="Scan indexed documents for schedule candidates",
)
def scan_schedule_candidates(
    payload: ScheduleScanRequest | None = None,
) -> ScheduleScanResponse:
    doc_id = payload.doc_id if payload else None
    source = payload.source if payload else None
    logger.info("Schedule scan endpoint called: doc_id=%s source=%s", doc_id, source)
    result = _service.scan(doc_id=doc_id, source=source)
    return ScheduleScanResponse(
        chunks_scanned=result["chunks_scanned"],
        candidates_extracted=result["candidates_extracted"],
        candidates_added=result["candidates_added"],
        candidates_skipped=result["candidates_skipped"],
        elapsed_ms=result["elapsed_ms"],
    )


@router.post(
    "/frontend/schedule-candidates/{candidate_id}/confirm",
    response_model=ScheduleStatusUpdateResponse,
    summary="Confirm a schedule candidate",
)
def confirm_schedule_candidate(candidate_id: str) -> ScheduleStatusUpdateResponse:
    logger.info("Schedule confirm endpoint called: candidate_id=%s", candidate_id)
    candidate = _service.confirm(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")
    return ScheduleStatusUpdateResponse(found=True, candidate=_to_item(candidate))


@router.post(
    "/frontend/schedule-candidates/{candidate_id}/dismiss",
    response_model=ScheduleStatusUpdateResponse,
    summary="Dismiss a schedule candidate",
)
def dismiss_schedule_candidate(candidate_id: str) -> ScheduleStatusUpdateResponse:
    logger.info("Schedule dismiss endpoint called: candidate_id=%s", candidate_id)
    candidate = _service.dismiss(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")
    return ScheduleStatusUpdateResponse(found=True, candidate=_to_item(candidate))


@router.get(
    "/frontend/schedule-candidates/export.ics",
    response_class=PlainTextResponse,
    summary="Export schedule candidates as an RFC 5545 .ics calendar (PRD FR-9)",
)
def export_schedule_candidates_ics(
    status: str = Query(default="confirmed", description="Which candidates to export: confirmed, pending, or all"),
) -> PlainTextResponse:
    if status not in {*_VALID_STATUSES, "all"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: pending, confirmed, dismissed, all",
        )
    logger.info("Schedule ICS export endpoint called: status=%s", status)
    listing_status = None if status == "all" else status
    candidates = _service.list_candidates(status=listing_status)
    ics_text = build_ics_calendar(candidates)
    return PlainTextResponse(
        content=ics_text,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="minddock-schedule.ics"'},
    )


@router.post(
    "/frontend/skills/schedule-extraction/run",
    response_model=ScheduleSkillRunResponse,
    summary="Run the schedule extraction skill",
)
def run_schedule_extraction(
    payload: ScheduleSkillRunRequest | None = None,
) -> ScheduleSkillRunResponse:
    doc_id = payload.doc_id if payload else None
    source = payload.source if payload else None
    logger.info("Schedule extraction skill run: doc_id=%s source=%s", doc_id, source)
    result = _service.scan(doc_id=doc_id, source=source)
    scan_response = ScheduleScanResponse(
        chunks_scanned=result["chunks_scanned"],
        candidates_extracted=result["candidates_extracted"],
        candidates_added=result["candidates_added"],
        candidates_skipped=result["candidates_skipped"],
        elapsed_ms=result["elapsed_ms"],
    )
    summary = (
        f"Scanned {result['chunks_scanned']} chunks, "
        f"extracted {result['candidates_extracted']} candidates, "
        f"added {result['candidates_added']} new."
    )
    return ScheduleSkillRunResponse(
        success=True,
        scan_result=scan_response,
        summary_text=summary,
    )
