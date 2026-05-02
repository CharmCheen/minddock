"""HTTP routes for all service endpoints."""

import logging
import os

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
    RuntimeConfigResponse,
    EffectiveRuntimeResponse,
    RuntimeConfigUpdateRequest,
    RuntimeConfigTestRequest,
    RuntimeConfigTestResponse,
    RuntimeProfileListResponse,
    MediaTranscriptConfigResponse,
    MediaTranscriptConfigTestResponse,
    MediaTranscriptConfigUpdateRequest,
    SearchRequest,
    SearchResponse,
    SkillDetailResponse,
    SkillListResponse,
    SourceSkillListResponse,
    SourceSkillManifestRequest,
    SourceSkillSummaryResponse,
    SourceSkillValidationResponse,
    SourceCatalogResponse,
    SourceChunkPageResponse,
    SourceDetailResponse,
    SummarizeRequest,
    SummarizeResponse,
    UnifiedExecutionRequestBody,
    UnifiedExecutionResponseBody,
)
from app.api.streaming import inject_heartbeat_events, project_run_events, serialize_client_event_sse
from app.application.events import ExecutionRunStatus
from app.application.client_events import ClientEventKind
from app.core.config import get_settings
from app.core.exceptions import RunNotFoundError, SkillNotFoundError, SkillNotPublicError
from app.core.logging import TRACE_LEVEL_NUM
from app.rag.vectorstore import health_check_vectorstore
from app.skills.source_registry import get_source_skill_registry
logger = logging.getLogger(__name__)
router = APIRouter()

frontend_facade = get_frontend_facade()


def _clear_runtime_caches() -> None:
    """Refresh runtime singletons after active runtime env overrides change."""

    from app.application import get_extension_registries
    from app.runtime.factory import get_runtime_factory
    from app.runtime.profiles import get_runtime_profile_registry
    from app.runtime.registry import get_runtime_registry

    global frontend_facade

    get_runtime_profile_registry.cache_clear()
    get_runtime_registry.cache_clear()
    get_runtime_factory.cache_clear()
    get_extension_registries.cache_clear()
    get_frontend_facade.cache_clear()
    frontend_facade = get_frontend_facade()


def _resolve_effective_runtime_response() -> EffectiveRuntimeResponse | None:
    """Project the resolver-selected default execution profile for status displays."""

    try:
        from app.runtime.models import RuntimeSelectionRequest

        result = frontend_facade.runtime_resolver.resolve(RuntimeSelectionRequest(task_type=TaskType.CHAT.value))
    except Exception:
        logger.exception("Failed to resolve effective runtime status")
        return None

    profile = result.profile
    resolved_base_url = os.environ.get("LLM_RUNTIME_BASE_URL") or profile.base_url
    resolved_model_name = os.environ.get("LLM_RUNTIME_MODEL") or result.binding.model_name
    return EffectiveRuntimeResponse(
        profile_id=result.binding.selected_profile_id,
        provider_kind=result.binding.provider_kind,
        model_name=resolved_model_name,
        base_url=resolved_base_url,
        source=result.binding.selection_reason or "runtime_profile",
        api_key_masked=bool(profile.api_key_env and os.environ.get(profile.api_key_env)),
    )


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
    db_ready = health_check_vectorstore()
    if not db_ready:
        return {
            "status": "initializing",
            "service": settings.app_name,
            "version": settings.app_version,
        }
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
    request = payload.to_application_request()
    debug_enabled = debug or payload.debug

    def sse_event_generator() -> dict[str, str]:
        import threading
        import time

        run_id_holder: list[str] = []
        run_holder: list[ExecutionRun] = []
        run_completed = threading.Event()
        run_error: list[Exception] = []

        def run_in_thread():
            try:

                def on_started(rid: str) -> None:
                    run_id_holder.append(rid)

                run = frontend_facade.execute_run(request, on_run_started=on_started)
                run_holder.append(run)
                # Fallback for consumers that don't invoke the callback
                if not run_id_holder:
                    run_id_holder.append(run.run_id)
            except Exception as exc:
                run_error.append(exc)
            finally:
                run_completed.set()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

        yielded_sequences: set[int] = set()
        poll_interval = 0.05  # seconds between registry polls

        while True:
            # Wait for the run to start (first event available) or complete
            run_completed.wait(timeout=2.0)

            # Progressive poll: once we know the run_id, continuously yield
            # newly-projected events from the registry so the client sees
            # progress while the run is still executing.
            if run_id_holder:
                events = frontend_facade.run_registry.get_recent_client_events(
                    run_id_holder[0], debug=debug_enabled
                )
                # Fallback for mocks / legacy paths that don't populate the registry
                if not events and run_holder:
                    events = project_run_events(run_holder[0], debug=debug_enabled)
                for evt in events:
                    if evt.sequence not in yielded_sequences:
                        yield serialize_client_event_sse(evt)
                        yielded_sequences.add(evt.sequence)

            if run_completed.is_set():
                break

            time.sleep(poll_interval)

        # After run completes, do a final poll to pick up any remaining events
        if run_id_holder:
            final_events = frontend_facade.run_registry.get_recent_client_events(
                run_id_holder[0], debug=debug_enabled
            )
            for evt in final_events:
                if evt.sequence not in yielded_sequences:
                    yield serialize_client_event_sse(evt)
                    yielded_sequences.add(evt.sequence)

            # Inject heartbeat if needed
            all_events = tuple(
                e for e in final_events if e.kind not in {ClientEventKind.HEARTBEAT}
            )
            hb_events = inject_heartbeat_events(
                all_events,
                run_id=run_id_holder[0],
                heartbeat_interval_seconds=frontend_facade.run_registry.config.heartbeat_interval_seconds,
            )
            for evt in hb_events:
                if evt.kind != ClientEventKind.HEARTBEAT:
                    continue
                if evt.sequence not in yielded_sequences:
                    yield serialize_client_event_sse(evt)
                    yielded_sequences.add(evt.sequence)

        if run_error:
            raise run_error[0]

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")


@router.get("/frontend/runtime-profiles", response_model=RuntimeProfileListResponse, summary="List frontend-selectable runtime profiles")
def list_runtime_profiles() -> RuntimeProfileListResponse:
    logger.debug("Runtime profile list endpoint called")
    result = frontend_facade.list_runtime_profiles()
    return present_runtime_profile_list_response(result)


@router.get(
    "/frontend/runtime-config",
    response_model=RuntimeConfigResponse,
    summary="Get the active user-configured runtime",
)
def get_runtime_config() -> RuntimeConfigResponse:
    from app.runtime.active_config import get_active_config, get_effective_runtime_status
    config = get_active_config()
    return RuntimeConfigResponse.from_config(config, get_effective_runtime_status(), _resolve_effective_runtime_response())


@router.get(
    "/frontend/media-transcript-config",
    response_model=MediaTranscriptConfigResponse,
    summary="Get the active media transcript provider configuration",
)
def get_media_transcript_config() -> MediaTranscriptConfigResponse:
    """Return sanitized media transcript config for frontend visibility.

    Priority: UI active config > environment settings > default.
    No API keys are returned.
    """
    from app.runtime.media_transcript_active_config import (
        CONFIG_FILE,
        get_active_media_transcript_config,
        get_effective_media_transcript_api_key,
        get_effective_media_transcript_base_url,
        get_effective_media_transcript_config_source,
        get_effective_media_transcript_model,
        get_effective_media_transcript_provider,
        get_effective_media_transcript_timeout,
        get_effective_local_asr_server_path,
        get_effective_local_asr_host,
        get_effective_local_asr_port,
        get_effective_local_asr_model,
        get_effective_local_asr_device,
        get_effective_local_asr_compute_type,
        get_effective_local_asr_auto_start,
        get_effective_local_asr_timeout_seconds,
    )

    settings = get_settings()
    active = get_active_media_transcript_config()

    api_key = get_effective_media_transcript_api_key(active, settings)
    base_url = get_effective_media_transcript_base_url(active, settings)
    provider = get_effective_media_transcript_provider(active, settings)
    model = get_effective_media_transcript_model(active, settings)
    timeout = get_effective_media_transcript_timeout(active, settings)
    config_source = get_effective_media_transcript_config_source(active, settings)

    # When no active config file exists, defer to settings for the enabled flag.
    # When the file exists (UI override), use the active config's value directly.
    if CONFIG_FILE.exists():
        enabled = active.enabled
    else:
        enabled = bool(getattr(settings, "media_transcript_enabled", False))

    return MediaTranscriptConfigResponse(
        enabled=enabled,
        provider=provider,
        api_key_configured=len(api_key) > 0,
        base_url=base_url,
        base_url_configured=len(base_url) > 0,
        model=model,
        timeout_seconds=timeout,
        config_source=config_source,
        local_asr_server_path=get_effective_local_asr_server_path(active, settings),
        local_asr_host=get_effective_local_asr_host(active, settings),
        local_asr_port=get_effective_local_asr_port(active, settings),
        local_asr_model=get_effective_local_asr_model(active, settings),
        local_asr_device=get_effective_local_asr_device(active, settings),
        local_asr_compute_type=get_effective_local_asr_compute_type(active, settings),
        local_asr_auto_start=get_effective_local_asr_auto_start(active, settings),
        local_asr_timeout_seconds=get_effective_local_asr_timeout_seconds(active, settings),
    )


@router.put(
    "/frontend/media-transcript-config",
    response_model=MediaTranscriptConfigResponse,
    summary="Update the active media transcript provider configuration",
)
def update_media_transcript_config(body: MediaTranscriptConfigUpdateRequest) -> MediaTranscriptConfigResponse:
    """Save the media transcript configuration.

    Security: api_key is NEVER written to disk. It is set in os.environ only.
    """
    from app.runtime.media_transcript_active_config import save_active_media_transcript_config

    save_active_media_transcript_config(
        provider=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        timeout_seconds=body.timeout_seconds,
        enabled=body.enabled,
        local_asr_server_path=body.local_asr_server_path,
        local_asr_host=body.local_asr_host,
        local_asr_port=body.local_asr_port,
        local_asr_model=body.local_asr_model,
        local_asr_device=body.local_asr_device,
        local_asr_compute_type=body.local_asr_compute_type,
        local_asr_auto_start=body.local_asr_auto_start,
        local_asr_timeout_seconds=body.local_asr_timeout_seconds,
    )

    # Refresh settings cache so get_settings() picks up new env vars
    get_settings.cache_clear()

    # Return the updated config
    return get_media_transcript_config()


@router.post(
    "/frontend/media-transcript-config/reset",
    response_model=MediaTranscriptConfigResponse,
    summary="Clear user-configured media transcript config and restore defaults",
)
def reset_media_transcript_config() -> MediaTranscriptConfigResponse:
    """Remove the persisted media transcript configuration and restore defaults."""
    from app.runtime.media_transcript_active_config import reset_active_media_transcript_config

    reset_active_media_transcript_config()

    # Refresh settings cache
    get_settings.cache_clear()

    return get_media_transcript_config()


@router.post(
    "/frontend/media-transcript-config/test",
    response_model=MediaTranscriptConfigTestResponse,
    summary="Test media transcript configuration completeness",
)
def test_media_transcript_config(body: MediaTranscriptConfigUpdateRequest) -> MediaTranscriptConfigTestResponse:
    """Validate that a media transcript configuration is complete.

    First version: configuration completeness check only, no real API calls.
    """
    if body.provider == "mock" or body.provider == "disabled":
        return MediaTranscriptConfigTestResponse(
            success=True,
            message=f"Provider '{body.provider}' does not require additional configuration.",
        )

    if body.provider == "local":
        # Local ASR completeness check
        server_path = body.local_asr_server_path.strip()
        if not server_path:
            return MediaTranscriptConfigTestResponse(
                success=False,
                message="Local ASR server path is required for the local provider.",
                error_kind="missing_local_asr_server_path",
            )
        host = body.local_asr_host.strip() or "127.0.0.1"
        port = body.local_asr_port
        if port < 1 or port > 65535:
            return MediaTranscriptConfigTestResponse(
                success=False,
                message="Local ASR port must be between 1 and 65535.",
                error_kind="invalid_local_asr_endpoint",
            )
        model = body.local_asr_model.strip()
        if not model:
            return MediaTranscriptConfigTestResponse(
                success=False,
                message="Model name is required for the local provider.",
                error_kind="missing_model",
            )
        return MediaTranscriptConfigTestResponse(
            success=True,
            message=f"Local ASR configuration is complete. Server path: {server_path}, endpoint: {host}:{port}, model: {model}.",
        )

    # provider == "api" — check completeness
    # Check api_key: either provided in body or already in env
    from app.runtime.media_transcript_active_config import get_active_media_transcript_config

    active = get_active_media_transcript_config()
    settings = get_settings()

    # api_key: body → active config env → settings → env
    effective_key = (body.api_key or "").strip()
    if not effective_key and active.enabled and active.api_key_source == "env":
        effective_key = os.environ.get("MEDIA_TRANSCRIPT_API_KEY", "").strip()
    if not effective_key:
        effective_key = str(getattr(settings, "media_transcript_api_key", "") or "").strip()
    if not effective_key:
        effective_key = os.environ.get("MEDIA_TRANSCRIPT_API_KEY", "").strip()

    # base_url: body → active → settings → env
    body_base_url = body.base_url.strip()
    if body_base_url:
        effective_base_url = body_base_url
    elif active.enabled and active.base_url:
        effective_base_url = active.base_url
    else:
        effective_base_url = str(getattr(settings, "media_transcript_api_base_url", "") or "").strip()
        if not effective_base_url:
            effective_base_url = os.environ.get("MEDIA_TRANSCRIPT_API_BASE_URL", "").strip()

    # model: body → active → settings → env
    body_model = body.model.strip()
    if body_model and body_model != "whisper-1":
        effective_model = body_model
    elif body_model == "" or (body_model == "whisper-1" and body.model == ""):
        # Explicitly empty model — treat as missing
        effective_model = ""
    elif active.enabled and active.model:
        effective_model = active.model
    else:
        effective_model = str(getattr(settings, "media_transcript_model", "") or "").strip()
        if not effective_model:
            effective_model = os.environ.get("MEDIA_TRANSCRIPT_MODEL", "").strip()

    if not effective_key:
        return MediaTranscriptConfigTestResponse(
            success=False,
            message="API key is required for the api provider. Enter a key or set MEDIA_TRANSCRIPT_API_KEY in the backend environment.",
            error_kind="missing_api_key",
        )

    if not effective_base_url:
        return MediaTranscriptConfigTestResponse(
            success=False,
            message="Base URL is required for the api provider.",
            error_kind="missing_base_url",
        )

    if not effective_model:
        return MediaTranscriptConfigTestResponse(
            success=False,
            message="Model name is required for the api provider.",
            error_kind="missing_model",
        )

    return MediaTranscriptConfigTestResponse(
        success=True,
        message=f"Configuration is complete. Provider 'api' with model '{effective_model}' is ready.",
    )


@router.put(
    "/frontend/runtime-config",
    response_model=RuntimeConfigResponse,
    summary="Update the active user-configured runtime",
)
def update_runtime_config(body: RuntimeConfigUpdateRequest) -> RuntimeConfigResponse:
    from app.runtime.active_config import (
        get_effective_runtime_status,
        save_active_config,
    )

    config = save_active_config(
        provider=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        enabled=body.enabled,
    )

    _clear_runtime_caches()

    return RuntimeConfigResponse.from_config(config, get_effective_runtime_status(), _resolve_effective_runtime_response())


@router.post(
    "/frontend/runtime-config/test",
    response_model=RuntimeConfigTestResponse,
    summary="Test connectivity to a runtime without persisting",
)
def test_runtime_config(body: RuntimeConfigTestRequest) -> RuntimeConfigTestResponse:
    """Validate that a runtime configuration is reachable.

    Performs the minimal possible request to verify the endpoint is accessible
    and the credentials are accepted. Does NOT run a full inference call.
    """
    # Basic URL validation
    if not body.base_url.strip():
        return RuntimeConfigTestResponse(
            success=False,
            message="base_url cannot be empty",
            error_kind="invalid_url",
        )
    if not body.base_url.startswith(("http://", "https://")):
        return RuntimeConfigTestResponse(
            success=False,
            message="base_url must start with http:// or https://",
            error_kind="invalid_url",
        )
    if not body.api_key.strip():
        return RuntimeConfigTestResponse(
            success=False,
            message="API key is required to test this runtime. Enter a key or set LLM_API_KEY in the backend environment.",
            error_kind="missing_api_key",
        )

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            api_key=body.api_key,
            base_url=body.base_url.rstrip("/"),
            model=body.model or "gpt-4o-mini",
            timeout=10.0,
            temperature=0,
            max_retries=1,
        )
        # Minimal call — just check the model list endpoint is reachable
        llm.invoke("hi")
        return RuntimeConfigTestResponse(
            success=True,
            message=f"Connection successful. Model '{body.model}' is reachable.",
        )
    except Exception as exc:
        error_message = str(exc).lower()
        if (
            "401" in error_message
            or "unauthorized" in error_message
            or "auth" in error_message
            or "api key" in error_message
        ):
            error_kind = "auth_failure"
            message = "Authentication failed. Check your API key."
        elif "404" in error_message or "not found" in error_message or "model" in error_message:
            error_kind = "model_not_found"
            message = f"Model '{body.model}' not found or not accessible at this endpoint."
        elif "timeout" in error_message or "timed out" in error_message:
            error_kind = "timeout"
            message = "Connection timed out. Check the base URL and your network."
        elif (
            "connection" in error_message
            or "network" in error_message
            or "refused" in error_message
            or "resolve" in error_message
        ):
            error_kind = "network_error"
            message = "Could not connect to the endpoint. Check the base URL."
        else:
            error_kind = "unknown"
            # Strip internal paths from the message for security
            import re

            safe_message = re.sub(r'[/\\]?\w+[/\\]\w+\.\w+', '<internal path>', error_message)
            message = f"Connection test failed: {safe_message[:120]}"

        return RuntimeConfigTestResponse(
            success=False,
            message=message,
            error_kind=error_kind,
        )


@router.post(
    "/frontend/runtime-config/reset",
    response_model=RuntimeConfigResponse,
    summary="Clear user-configured runtime and restore defaults",
)
def reset_runtime_config() -> RuntimeConfigResponse:
    """Remove the persisted runtime configuration and restore the system default."""
    from app.runtime.active_config import (
        get_effective_runtime_status,
        save_active_config,
    )

    # Write a disabled default config (api_key never written to disk)
    config = save_active_config(
        provider="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="",
        model="gpt-4o-mini",
        enabled=False,
    )

    _clear_runtime_caches()

    return RuntimeConfigResponse.from_config(config, get_effective_runtime_status(), _resolve_effective_runtime_response())


@router.get("/frontend/skills", response_model=SkillListResponse, summary="List frontend-discoverable skills")
def list_skills() -> SkillListResponse:
    logger.debug("Skill catalog list endpoint called")
    result = frontend_facade.list_skills()
    return present_skill_list_response(result)


@router.get("/frontend/source-skills", response_model=SourceSkillListResponse, summary="List source skill manifests and built-ins")
def list_source_skills(
    include_future: bool = Query(default=True),
    include_local: bool = Query(default=True),
) -> SourceSkillListResponse:
    logger.debug("Source skill catalog list endpoint called")
    skills = get_source_skill_registry().list_skills(include_future=include_future, include_local=include_local)
    return SourceSkillListResponse.from_infos(skills)


@router.post("/frontend/source-skills/validate", response_model=SourceSkillValidationResponse, summary="Validate a local source skill manifest")
def validate_source_skill_manifest(payload: SourceSkillManifestRequest) -> SourceSkillValidationResponse:
    logger.debug("Source skill manifest validate endpoint called")
    result = get_source_skill_registry().validate_manifest(payload.manifest)
    return SourceSkillValidationResponse.from_result(result)


@router.post("/frontend/source-skills/register", response_model=SourceSkillValidationResponse, summary="Register a local source skill manifest")
def register_source_skill_manifest(payload: SourceSkillManifestRequest) -> SourceSkillValidationResponse:
    logger.info("Source skill manifest register endpoint called")
    result = get_source_skill_registry().register_manifest(payload.manifest)
    return SourceSkillValidationResponse.from_result(result)


@router.get("/frontend/source-skills/{skill_id}", response_model=SourceSkillSummaryResponse, summary="Get one source skill")
def get_source_skill_detail(skill_id: str) -> SourceSkillSummaryResponse:
    logger.debug("Source skill detail endpoint called: skill_id=%s", skill_id)
    result = get_source_skill_registry().get_skill(skill_id)
    if result is None:
        raise SkillNotFoundError(detail=f"Source skill '{skill_id}' was not found.")
    return SourceSkillSummaryResponse.from_info(result)


@router.post("/frontend/source-skills/{skill_id}/enable", response_model=SourceSkillValidationResponse, summary="Enable a local source skill")
def enable_source_skill(skill_id: str) -> SourceSkillValidationResponse:
    logger.info("Source skill enable endpoint called: skill_id=%s", skill_id)
    result = get_source_skill_registry().enable_skill(skill_id)
    return SourceSkillValidationResponse.from_result(result)


@router.post("/frontend/source-skills/{skill_id}/disable", response_model=SourceSkillValidationResponse, summary="Disable a local source skill")
def disable_source_skill(skill_id: str) -> SourceSkillValidationResponse:
    logger.info("Source skill disable endpoint called: skill_id=%s", skill_id)
    result = get_source_skill_registry().disable_skill(skill_id)
    return SourceSkillValidationResponse.from_result(result)


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
