"""Helpers for source-state lookup and evidence freshness resolution."""

from __future__ import annotations

from dataclasses import replace

from app.rag.retrieval_models import ComparedPoint, EvidenceFreshness, EvidenceObject, GroundedAnswer, GroundedCompareResult
from app.rag.source_models import CatalogQuery, SourceDetail, SourceState
from app.rag.vectorstore import get_vectorstore, list_source_details


def get_current_source_state(
    *,
    doc_id: str | None = None,
    source: str | None = None,
    collection=None,
) -> SourceState | None:
    """Return the current indexed state for one source, if it exists."""

    detail = _resolve_detail(doc_id=doc_id, source=source, collection=collection)
    if detail is None:
        return None
    return detail.entry.state


def refresh_grounded_answer_freshness(
    grounded_answer: GroundedAnswer,
    *,
    collection=None,
) -> GroundedAnswer:
    """Refresh evidence freshness against the current source catalog state."""

    try:
        refreshed = tuple(
            refresh_evidence_freshness(item, collection=collection)
            for item in grounded_answer.evidence
        )
    except Exception:
        return grounded_answer
    return replace(grounded_answer, evidence=refreshed)


def refresh_compare_result_freshness(
    compare_result: GroundedCompareResult,
    *,
    collection=None,
) -> GroundedCompareResult:
    """Refresh all compare evidence freshness against the current source catalog state."""

    try:
        common_points = tuple(
            _refresh_compared_point(point, collection=collection)
            for point in compare_result.common_points
        )
        differences = tuple(
            _refresh_compared_point(point, collection=collection)
            for point in compare_result.differences
        )
        conflicts = tuple(
            _refresh_compared_point(point, collection=collection)
            for point in compare_result.conflicts
        )
    except Exception:
        return compare_result
    return replace(
        compare_result,
        common_points=common_points,
        differences=differences,
        conflicts=conflicts,
    )


def refresh_evidence_freshness(
    evidence: EvidenceObject,
    *,
    collection=None,
) -> EvidenceObject:
    """Compare one evidence object against the current indexed source state."""

    detail = _resolve_detail(doc_id=evidence.doc_id, source=evidence.source, collection=collection)
    if detail is None or detail.entry.state is None:
        return replace(evidence, freshness=EvidenceFreshness.INVALIDATED)

    current_state = detail.entry.state
    chunk_ids = _chunk_ids_for_doc(detail.entry.doc_id, collection=collection)
    if evidence.chunk_id not in chunk_ids:
        return replace(evidence, freshness=EvidenceFreshness.INVALIDATED)

    current_version = current_state.current_version or current_state.content_hash
    evidence_version = evidence.source_version or evidence.content_hash
    if evidence_version and current_version and evidence_version == current_version:
        return replace(evidence, freshness=EvidenceFreshness.FRESH)
    if evidence_version is None and current_version is None:
        return replace(evidence, freshness=EvidenceFreshness.FRESH)
    return replace(evidence, freshness=EvidenceFreshness.STALE_POSSIBLE)


def _refresh_compared_point(
    point: ComparedPoint,
    *,
    collection=None,
) -> ComparedPoint:
    return replace(
        point,
        left_evidence=tuple(refresh_evidence_freshness(item, collection=collection) for item in point.left_evidence),
        right_evidence=tuple(refresh_evidence_freshness(item, collection=collection) for item in point.right_evidence),
    )


def _resolve_detail(*, doc_id: str | None, source: str | None, collection=None) -> SourceDetail | None:
    target_doc_id = (doc_id or "").strip()
    target_source = (source or "").strip()
    active_collection = collection or get_vectorstore()
    if hasattr(active_collection, "list_source_details"):
        details = active_collection.list_source_details(CatalogQuery())
    else:
        details = list_source_details(CatalogQuery())
    for detail in details:
        if target_doc_id and detail.entry.doc_id == target_doc_id:
            return detail
        if target_source and detail.entry.source == target_source:
            return detail
    return None


def _chunk_ids_for_doc(doc_id: str, *, collection=None) -> set[str]:
    active_collection = collection or get_vectorstore()
    if hasattr(active_collection, "list_document_chunk_ids"):
        return set(active_collection.list_document_chunk_ids(doc_id))
    return set()
