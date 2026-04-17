"""Boundary-layer presenters that map service/domain results to API schemas."""

from __future__ import annotations

from app.application.artifacts import ArtifactMapper
from app.api.streaming import project_run_events
from app.api.schemas import (
    CancelRunResponse,
    ChatResponse,
    ClientEventResponseItem,
    DeleteSourceResponse,
    CompareResponse,
    ErrorResponse,
    IngestResponse,
    ReingestSourceResponse,
    RunEventListResponse,
    RuntimeProfileListResponse,
    RunSummaryResponse,
    SkillDetailResponse,
    SkillListResponse,
    SearchResponse,
    SourceCatalogResponse,
    SourceCatalogItem,
    SourceChunkPageResponse,
    SourceDetailResponse,
    SummarizeResponse,
    UnifiedExecutionResponseBody,
)
from app.application.models import UnifiedExecutionResponse
from app.application.run_control import ManagedRun
from app.services.participation import extract_participating_doc_ids, load_projected_sources
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    CompareServiceResult,
    DeleteSourceServiceResult,
    IngestServiceResult,
    ReingestSourceServiceResult,
    SearchServiceResult,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SummarizeServiceResult,
)


def present_search_response(result: SearchServiceResult) -> SearchResponse:
    return SearchResponse.from_result(result)


def present_search_response_from_unified(
    *,
    query: str,
    top_k: int,
    result: UnifiedExecutionResponse,
) -> SearchResponse:
    artifact = ArtifactMapper.first_search_results(result.artifacts)
    if artifact is None:
        return SearchResponse(query=query, top_k=top_k, hits=[])
    return SearchResponse.from_search_artifact(query=query, top_k=top_k, artifact=artifact)


def present_chat_response(result: ChatServiceResult) -> ChatResponse:
    return ChatResponse.from_result(result)


def present_summarize_response(result: SummarizeServiceResult) -> SummarizeResponse:
    return SummarizeResponse.from_result(result)


def present_compare_response(result: CompareServiceResult) -> CompareResponse:
    return CompareResponse.from_result(result)


def present_ingest_response(result: IngestServiceResult) -> IngestResponse:
    return IngestResponse.from_result(result)


def present_source_catalog_response(result: CatalogServiceResult) -> SourceCatalogResponse:
    return SourceCatalogResponse.from_result(result)


def present_source_detail_response(result: SourceDetailServiceResult) -> SourceDetailResponse:
    return SourceDetailResponse.from_result(result)


def present_source_chunk_page_response(result: SourceInspectServiceResult) -> SourceChunkPageResponse:
    return SourceChunkPageResponse.from_result(result)


def present_delete_source_response(result: DeleteSourceServiceResult) -> DeleteSourceResponse:
    return DeleteSourceResponse.from_result(result)


def present_reingest_source_response(result: ReingestSourceServiceResult) -> ReingestSourceResponse:
    return ReingestSourceResponse.from_result(result)


def present_unified_execution_response(result: UnifiedExecutionResponse) -> UnifiedExecutionResponseBody:
    participating_doc_ids = extract_participating_doc_ids(result.citations)
    participating_sources = [
        SourceCatalogItem.from_entry(entry)
        for entry in load_projected_sources(participating_doc_ids)
    ]
    return UnifiedExecutionResponseBody.from_result(result, participating_sources=participating_sources)


def present_run_summary_response(result: ManagedRun) -> RunSummaryResponse:
    final_response = None
    if result.final_response is not None:
        final_response = {
            "task_type": result.final_response.task_type.value,
            "artifact_count": len(result.final_response.artifacts),
            "primary_artifact_kind": result.final_response.execution_summary.primary_artifact_kind or result.final_response.metadata.primary_artifact_kind,
        }
    error = None if result.error_summary is None else {"error": result.error_summary.error, "detail": result.error_summary.detail}
    return RunSummaryResponse(
        run_id=result.run_id,
        status=result.status.value,
        created_at=result.created_at.isoformat(),
        updated_at=result.updated_at.isoformat(),
        selected_runtime=result.selected_runtime,
        selected_profile_id=result.selected_profile_id,
        selected_provider_kind=result.selected_provider_kind,
        event_count=result.event_count,
        cancellation_requested=result.cancellation_requested,
        has_final_response=result.has_final_response,
        final_response=final_response,
        error=error,
    )


def present_run_event_list_response(result: ManagedRun, *, debug: bool = False) -> RunEventListResponse:
    events = result.recent_client_events if not debug else project_run_events(
        type("RunCompat", (), {"events": tuple(result.internal_events), "run_id": result.run_id})(),
        debug=True,
    )
    return RunEventListResponse(
        run_id=result.run_id,
        status=result.status.value,
        event_count=len(events),
        items=[ClientEventResponseItem.from_client_event(event) for event in events],
    )


def present_cancel_run_response(result: ManagedRun, *, accepted: bool, detail: str) -> CancelRunResponse:
    return CancelRunResponse(
        run_id=result.run_id,
        status=result.status.value,
        cancellation_requested=result.cancellation_requested,
        accepted=accepted,
        detail=detail,
    )


def present_runtime_profile_list_response(result) -> RuntimeProfileListResponse:
    return RuntimeProfileListResponse.from_summaries(result)


def present_skill_list_response(result) -> SkillListResponse:
    return SkillListResponse.from_entries(result)


def present_skill_detail_response(result) -> SkillDetailResponse:
    return SkillDetailResponse.from_detail(result)


def present_error_response(
    *,
    error: str,
    detail: str,
    request_id: str | None = None,
    category: str | None = None,
) -> ErrorResponse:
    return ErrorResponse.from_parts(
        error=error,
        detail=detail,
        request_id=request_id,
        category=category,
    )
