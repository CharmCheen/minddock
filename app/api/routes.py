"""HTTP routes for all service endpoints."""

import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.application import get_frontend_facade
from app.application.models import CitationPolicy, RetrievalOptions, SkillPolicy, TaskType, UnifiedExecutionRequest
from app.api.presenters import (
    present_cancel_run_response,
    present_delete_source_response,
    present_chat_response,
    present_compare_response,
    present_ingest_response,
    present_reingest_source_response,
    present_run_event_list_response,
    present_runtime_profile_list_response,
    present_run_summary_response,
    present_skill_detail_response,
    present_skill_list_response,
    present_search_response,
    present_search_response_from_unified,
    present_source_catalog_response,
    present_source_chunk_page_response,
    present_source_detail_response,
    present_summarize_response,
    present_unified_execution_response,
)
from app.api.schemas import (
    CancelRunResponse,
    ChatRequest,
    ChatResponse,
    CompareRequest,
    CompareResponse,
    DeleteSourceResponse,
    IngestRequest,
    IngestResponse,
    ReingestSourceResponse,
    RunEventListResponse,
    RunSummaryResponse,
    RuntimeProfileListResponse,
    SearchRequest,
    SearchResponse,
    SkillDetailResponse,
    SkillListResponse,
    SourceCatalogResponse,
    SourceChunkPageResponse,
    SourceDetailResponse,
    SummarizeRequest,
    SummarizeResponse,
    UnifiedExecutionRequestBody,
    UnifiedExecutionResponseBody,
)
from app.api.streaming import inject_heartbeat_events, iter_sse_chunks, project_run_events
from app.application.events import ExecutionRunStatus
from app.core.config import get_settings
from app.core.exceptions import RunNotFoundError, SkillNotFoundError, SkillNotPublicError
from app.core.logging import TRACE_LEVEL_NUM
logger = logging.getLogger(__name__)
router = APIRouter()

frontend_facade = get_frontend_facade()


@router.get("/", summary="Service info")
def root() -> dict[str, str]:
    settings = get_settings()
    logger.log(TRACE_LEVEL_NUM, "Root endpoint called")
    return {
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/health", summary="Health check")
def health() -> dict[str, str]:
    settings = get_settings()
    logger.log(TRACE_LEVEL_NUM, "Health endpoint called")
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.post("/ingest", response_model=IngestResponse, summary="Ingest knowledge base documents")
def ingest(payload: IngestRequest) -> IngestResponse:
    logger.info("Ingest endpoint called: rebuild=%s url_count=%d", payload.rebuild, len(payload.urls))
    result = frontend_facade.knowledge_base.ingest(rebuild=payload.rebuild, urls=payload.urls)
    return present_ingest_response(result)


@router.get("/sources", response_model=SourceCatalogResponse, summary="List indexed sources")
def list_sources(source_type: str | None = Query(default=None)) -> SourceCatalogResponse:
    logger.debug("Source catalog endpoint called: source_type=%s", source_type)
    result = frontend_facade.knowledge_base.list_sources(source_type=source_type)
    return present_source_catalog_response(result)


@router.get("/sources/by-source", response_model=SourceDetailResponse, summary="Get indexed source detail by source")
def get_source_by_source(
    source: str = Query(...),
    include_admin_metadata: bool = Query(default=False),
) -> SourceDetailResponse:
    logger.debug("Source detail endpoint called by source: source=%s include_admin_metadata=%s", source, include_admin_metadata)
    result = frontend_facade.knowledge_base.get_source_detail(source=source, include_admin_metadata=include_admin_metadata)
    return present_source_detail_response(result)


@router.get("/sources/by-source/chunks", response_model=SourceChunkPageResponse, summary="Inspect source chunks by source")
def get_source_chunks_by_source(
    source: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_admin_metadata: bool = Query(default=False),
) -> SourceChunkPageResponse:
    logger.debug(
        "Source chunk inspect endpoint called by source: source=%s limit=%d offset=%d include_admin_metadata=%s",
        source,
        limit,
        offset,
        include_admin_metadata,
    )
    result = frontend_facade.knowledge_base.inspect_source(
        source=source,
        limit=limit,
        offset=offset,
        include_admin_metadata=include_admin_metadata,
    )
    return present_source_chunk_page_response(result)


@router.delete("/sources/by-source", response_model=DeleteSourceResponse, summary="Delete indexed source by source")
def delete_source_by_source(source: str = Query(...)) -> DeleteSourceResponse:
    logger.info("Delete source endpoint called by source: source=%s", source)
    result = frontend_facade.knowledge_base.delete_source(source=source)
    return present_delete_source_response(result)


@router.post("/sources/by-source/reingest", response_model=ReingestSourceResponse, summary="Reingest indexed source by source")
def reingest_source_by_source(source: str = Query(...)) -> ReingestSourceResponse:
    logger.info("Reingest source endpoint called by source: source=%s", source)
    result = frontend_facade.knowledge_base.reingest_source(source=source)
    return present_reingest_source_response(result)


@router.post("/search", response_model=SearchResponse, summary="Semantic search with citations")
def search(payload: SearchRequest) -> SearchResponse:
    logger.debug("Search endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.to_retrieval_filters() if payload.filters else None
    result = frontend_facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.SEARCH,
            user_input=payload.query,
            retrieval=RetrievalOptions(top_k=payload.top_k, filters=filters),
            citation_policy=CitationPolicy.PREFERRED,
            skill_policy=SkillPolicy(),
            include_metadata=True,
        )
    )
    return present_search_response_from_unified(query=payload.query, top_k=payload.top_k, result=result)


@router.post("/chat", response_model=ChatResponse, summary="Grounded chat with citations")
def chat(payload: ChatRequest) -> ChatResponse:
    logger.debug("Chat endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.to_retrieval_filters() if payload.filters else None
    result = frontend_facade.execute_chat_request(query=payload.query, top_k=payload.top_k, filters=filters)
    return present_chat_response(result)


@router.post("/summarize", response_model=SummarizeResponse, summary="Grounded summarization")
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    logger.debug("Summarize endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.to_retrieval_filters() if payload.filters else None
    result = frontend_facade.execute_summarize_request(
        topic=payload.resolved_topic(),
        top_k=payload.top_k,
        filters=filters,
        mode=payload.mode,
        output_format=payload.output_format,
    )
    return present_summarize_response(result)


@router.post("/compare", response_model=CompareResponse, summary="Grounded document compare")
def compare(payload: CompareRequest) -> CompareResponse:
    logger.debug("Compare endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.to_retrieval_filters() if payload.filters else None
    result = frontend_facade.execute_compare_request(question=payload.question, top_k=payload.top_k, filters=filters)
    return present_compare_response(result)


@router.get("/sources/{doc_id}", response_model=SourceDetailResponse, summary="Get indexed source detail by doc id")
def get_source(doc_id: str, include_admin_metadata: bool = Query(default=False)) -> SourceDetailResponse:
    logger.debug("Source detail endpoint called: doc_id=%s include_admin_metadata=%s", doc_id, include_admin_metadata)
    result = frontend_facade.knowledge_base.get_source_detail(doc_id=doc_id, include_admin_metadata=include_admin_metadata)
    return present_source_detail_response(result)


@router.get("/sources/{doc_id}/chunks", response_model=SourceChunkPageResponse, summary="Inspect indexed source chunks by doc id")
def get_source_chunks(
    doc_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_admin_metadata: bool = Query(default=False),
) -> SourceChunkPageResponse:
    logger.debug(
        "Source chunk inspect endpoint called: doc_id=%s limit=%d offset=%d include_admin_metadata=%s",
        doc_id,
        limit,
        offset,
        include_admin_metadata,
    )
    result = frontend_facade.knowledge_base.inspect_source(
        doc_id=doc_id,
        limit=limit,
        offset=offset,
        include_admin_metadata=include_admin_metadata,
    )
    return present_source_chunk_page_response(result)


@router.delete("/sources/{doc_id}", response_model=DeleteSourceResponse, summary="Delete indexed source by doc id")
def delete_source(doc_id: str) -> DeleteSourceResponse:
    logger.info("Delete source endpoint called: doc_id=%s", doc_id)
    result = frontend_facade.knowledge_base.delete_source(doc_id=doc_id)
    return present_delete_source_response(result)


@router.post("/sources/{doc_id}/reingest", response_model=ReingestSourceResponse, summary="Reingest indexed source by doc id")
def reingest_source(doc_id: str) -> ReingestSourceResponse:
    logger.info("Reingest source endpoint called: doc_id=%s", doc_id)
    result = frontend_facade.knowledge_base.reingest_source(doc_id=doc_id)
    return present_reingest_source_response(result)


@router.post("/frontend/execute", response_model=UnifiedExecutionResponseBody, summary="Unified frontend execution entrypoint")
def execute_frontend_task(payload: UnifiedExecutionRequestBody) -> UnifiedExecutionResponseBody:
    logger.debug("Unified execute endpoint called: task_type=%s", payload.task_type)
    result = frontend_facade.execute(payload.to_application_request())
    return present_unified_execution_response(result)


@router.post("/frontend/execute/stream", summary="Projected client event stream for unified execution")
def execute_frontend_task_stream(
    payload: UnifiedExecutionRequestBody,
    debug: bool = Query(default=False, description="When true, include debug-visible client events."),
) -> StreamingResponse:
    logger.debug("Unified stream endpoint called: task_type=%s debug=%s", payload.task_type, debug)
    run = frontend_facade.execute_run(payload.to_application_request())
    projected_events = frontend_facade.run_registry.get_recent_client_events(run.run_id, debug=debug or payload.debug)
    if not projected_events:
        projected_events = project_run_events(run, debug=debug or payload.debug)
    projected_events = inject_heartbeat_events(
        projected_events,
        run_id=run.run_id,
        heartbeat_interval_seconds=frontend_facade.run_registry.config.heartbeat_interval_seconds,
    )
    return StreamingResponse(iter_sse_chunks(projected_events), media_type="text/event-stream")


@router.get("/frontend/runtime-profiles", response_model=RuntimeProfileListResponse, summary="List frontend-selectable runtime profiles")
def list_runtime_profiles() -> RuntimeProfileListResponse:
    logger.debug("Runtime profile list endpoint called")
    result = frontend_facade.list_runtime_profiles()
    return present_runtime_profile_list_response(result)


@router.get("/frontend/skills", response_model=SkillListResponse, summary="List frontend-discoverable skills")
def list_skills() -> SkillListResponse:
    logger.debug("Skill catalog list endpoint called")
    result = frontend_facade.list_skills()
    return present_skill_list_response(result)


@router.get("/frontend/skills/{skill_id}", response_model=SkillDetailResponse, summary="Get one frontend-safe skill detail")
def get_skill_detail(skill_id: str) -> SkillDetailResponse:
    logger.debug("Skill detail endpoint called: skill_id=%s", skill_id)
    result = frontend_facade.get_skill_detail(skill_id)
    if result is None:
        raise SkillNotFoundError(detail=f"Skill '{skill_id}' was not found.")
    if not result.safe_for_public_listing:
        raise SkillNotPublicError(detail=f"Skill '{skill_id}' is not available for public listing.")
    return present_skill_detail_response(result)


@router.get("/frontend/runs/{run_id}", response_model=RunSummaryResponse, summary="Get transient run status")
def get_run_status(run_id: str) -> RunSummaryResponse:
    logger.debug("Run status endpoint called: run_id=%s", run_id)
    run = frontend_facade.run_registry.get(run_id)
    if run is None:
        raise RunNotFoundError(detail=f"Run '{run_id}' was not found.")
    return present_run_summary_response(run)


@router.get("/frontend/runs/{run_id}/events", response_model=RunEventListResponse, summary="Replay recent client events for a run")
def get_run_events(run_id: str, debug: bool = Query(default=False)) -> RunEventListResponse:
    logger.debug("Run replay endpoint called: run_id=%s debug=%s", run_id, debug)
    run = frontend_facade.run_registry.get(run_id)
    if run is None:
        raise RunNotFoundError(detail=f"Run '{run_id}' was not found.")
    return present_run_event_list_response(run, debug=debug)


@router.post("/frontend/runs/{run_id}/cancel", response_model=CancelRunResponse, summary="Request cancellation for a transient run")
def cancel_run(run_id: str) -> CancelRunResponse:
    logger.debug("Run cancel endpoint called: run_id=%s", run_id)
    run = frontend_facade.run_registry.get(run_id)
    if run is None:
        raise RunNotFoundError(detail=f"Run '{run_id}' was not found.")
    updated = frontend_facade.run_registry.request_cancellation(run_id)
    assert updated is not None
    if updated.status in {ExecutionRunStatus.COMPLETED, ExecutionRunStatus.FAILED, ExecutionRunStatus.CANCELLED, ExecutionRunStatus.EXPIRED}:
        return present_cancel_run_response(updated, accepted=False, detail="Run is no longer active; cancellation request recorded but will not change the outcome.")
    return present_cancel_run_response(updated, accepted=True, detail="Cancellation requested. Best-effort cancellation will be attempted at safe execution boundaries.")
