"""Unit tests for API boundary presenters."""

import app.api.presenters as presenters_module

from app.api.presenters import (
    present_delete_source_response,
    present_chat_response,
    present_error_response,
    present_ingest_response,
    present_reingest_source_response,
    present_runtime_profile_list_response,
    present_search_response,
    present_search_response_from_unified,
    present_source_catalog_response,
    present_source_chunk_page_response,
    present_source_detail_response,
    present_summarize_response,
    present_unified_execution_response,
)
from app.application.artifacts import ArtifactKind, SearchResultItemArtifact, SearchResultsArtifact, SkillResultArtifact, TextArtifact
from app.application.events import ArtifactEmittedPayload, EventCollector, ExecutionEventKind, RunCompletedPayload, RunStartedPayload
from app.application.models import UnifiedExecutionResponse, TaskType
from app.rag.retrieval_models import CitationRecord, RetrievedChunk, SearchHitRecord, SearchResult
from app.runtime.models import RuntimeProfileSummary
from app.rag.source_models import (
    DeleteSourceResult,
    FailedSourceInfo,
    IngestBatchResult,
    IngestSourceResult,
    SourceCatalogEntry,
    SourceChunkPage,
    SourceChunkPreview,
    SourceDescriptor,
    SourceDetail,
    SourceInspectResult,
    SourceParticipationState,
)
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    DeleteSourceServiceResult,
    IngestServiceResult,
    ReingestSourceServiceResult,
    SearchServiceResult,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SummarizeServiceResult,
    UseCaseMetadata,
)


def test_present_search_response_from_formal_result() -> None:
    chunk = RetrievedChunk(
        text="text",
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        source_type="file",
    )
    response = present_search_response(
        SearchServiceResult(
            search_result=SearchResult(
                query="q",
                top_k=1,
                hits=[
                    SearchHitRecord(
                        chunk=chunk,
                        citation=CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text"),
                    )
                ],
            ),
            metadata=UseCaseMetadata(retrieved_count=1),
        )
    )

    assert response.query == "q"
    assert response.hits[0].citation.source == "kb/doc.md"


def test_present_ingest_response_marks_partial_failure() -> None:
    response = present_ingest_response(
        IngestServiceResult(
            batch=IngestBatchResult(
                source_results=[
                    IngestSourceResult(
                        descriptor=SourceDescriptor(source="doc.md", source_type="file"),
                        ok=True,
                        chunks_upserted=1,
                    ),
                    IngestSourceResult(
                        descriptor=SourceDescriptor(source="https://example.com", source_type="url"),
                        ok=False,
                        failure=FailedSourceInfo(
                            source="https://example.com",
                            source_type="url",
                            reason="network failed",
                        ),
                    ),
                ]
            ),
            metadata=UseCaseMetadata(partial_failure=True),
        )
    )

    assert response.partial_failure is True
    assert response.failed_sources[0].reason == "network failed"


def test_present_chat_and_summarize_response_from_service_dicts() -> None:
    chat = present_chat_response(
        ChatServiceResult(
            answer="answer",
            citations=[CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text")],
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded"),
        )
    )
    summarize = present_summarize_response(
        SummarizeServiceResult(
            summary="summary",
            citations=[CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text")],
            metadata=UseCaseMetadata(retrieved_count=1, mode="map_reduce", output_format="mermaid"),
            structured_output="mindmap",
        )
    )

    assert chat.mode == "grounded"
    assert summarize.output_format == "mermaid"


def test_present_error_response_sets_category() -> None:
    error = present_error_response(error="search_error", detail="failed", request_id="abc")
    assert error.category == "search_error"
    assert error.request_id == "abc"


def test_present_catalog_detail_delete_and_reingest_responses() -> None:
    catalog = present_source_catalog_response(
        CatalogServiceResult(
            entries=[
                SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                )
            ]
        )
    )
    detail = present_source_detail_response(
        SourceDetailServiceResult(
            found=True,
            detail=SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                ),
                representative_metadata={"title": "notes"},
            ),
        )
    )
    delete = present_delete_source_response(
        DeleteSourceServiceResult(result=DeleteSourceResult(found=True, doc_id="d1", source="notes.md", source_type="file", deleted_chunks=2))
    )
    reingest = present_reingest_source_response(
        ReingestSourceServiceResult(
            found=True,
            source_result=IngestSourceResult(
                descriptor=SourceDescriptor(source="notes.md", source_type="file"),
                ok=True,
                chunks_upserted=2,
                chunks_deleted=1,
            ),
        )
    )
    inspect = present_source_chunk_page_response(
        SourceInspectServiceResult(
            found=True,
            inspect=SourceInspectResult(
                detail=SourceDetail(
                    entry=SourceCatalogEntry(
                        doc_id="d1",
                        source="notes.md",
                        source_type="file",
                        title="notes",
                        chunk_count=2,
                    ),
                    representative_metadata={"title": "notes"},
                ),
                chunk_page=SourceChunkPage(
                    total_chunks=2,
                    returned_chunks=1,
                    limit=1,
                    offset=0,
                    chunks=[
                        SourceChunkPreview(
                            chunk_id="d1:0",
                            chunk_index=0,
                            preview_text="chunk preview",
                            title="notes",
                            section="Storage",
                            location="Storage",
                            ref="notes > Storage",
                            admin_metadata={"doc_id": "d1"},
                        )
                    ],
                ),
                include_admin_metadata=True,
                admin_metadata={"doc_id": "d1"},
            ),
        )
    )

    assert catalog.total == 1
    assert detail.item is not None and detail.item.source == "notes.md"
    assert inspect.total_chunks == 2
    assert inspect.chunks[0].chunk_id == "d1:0"
    assert delete.deleted_chunks == 2
    assert reingest.ok is True


def test_present_runtime_profile_list_response() -> None:
    response = present_runtime_profile_list_response(
        (
            RuntimeProfileSummary(
                profile_id="default_cloud",
                display_name="Default Cloud",
                provider_kind="openai_compatible",
                model_name="gpt-4o-mini",
                tags=("cloud",),
                enabled=True,
                capabilities=("supports_chat",),
            ),
        )
    )

    assert response.total == 1
    assert response.items[0].profile_id == "default_cloud"


def test_present_unified_execution_response_maps_artifacts() -> None:
    original_loader = presenters_module.load_projected_sources
    presenters_module.load_projected_sources = lambda participating_doc_ids: ()
    response = present_unified_execution_response(
        UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(
                TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="answer"),
                SkillResultArtifact(
                    artifact_id="skill-1",
                    kind=ArtifactKind.SKILL_RESULT,
                    skill_name="echo",
                    payload={"text": "answer"},
                    summary_text="answer",
                ),
            ),
            metadata=UseCaseMetadata(
                artifact_kinds_returned=("text", "skill_result"),
                primary_artifact_kind="text",
                artifact_count=2,
                skill_artifact_count=1,
            ),
        )
    )
    presenters_module.load_projected_sources = original_loader

    assert response.artifacts[0].kind == "text"
    assert response.artifacts[0].content["text"] == "answer"
    assert response.artifacts[1].content["skill_name"] == "echo"
    assert response.metadata.artifact_count == 2


def test_present_search_response_from_unified_uses_search_results_artifact() -> None:
    response = present_search_response_from_unified(
        query="q",
        top_k=1,
        result=UnifiedExecutionResponse(
            task_type=TaskType.SEARCH,
            artifacts=(
                SearchResultsArtifact(
                    artifact_id="search-1",
                    kind=ArtifactKind.SEARCH_RESULTS,
                    items=(
                        SearchResultItemArtifact(
                            chunk_id="c1",
                            doc_id="d1",
                            source="kb/doc.md",
                            source_type="file",
                            title="doc",
                            snippet="text",
                            score=0.1,
                        ),
                    ),
                    total=1,
                    offset=0,
                    limit=1,
                ),
            ),
        ),
    )

    assert response.query == "q"
    assert response.hits[0].chunk_id == "c1"


def test_present_unified_execution_response_maps_events() -> None:
    original_loader = presenters_module.load_projected_sources
    presenters_module.load_projected_sources = lambda participating_doc_ids: ()
    collector = EventCollector(run_id="run-123", task_type="chat")
    collector.emit(
        kind=ExecutionEventKind.RUN_STARTED,
        payload=RunStartedPayload(
            request=type(
                "ReqSummary",
                (),
                {
                    "task_type": "chat",
                    "user_input_preview": "hello",
                    "output_mode": "text",
                    "top_k": 5,
                    "citation_policy": "preferred",
                    "skill_policy": "disabled",
                },
            )(),
        ),
    )
    collector.emit(
        kind=ExecutionEventKind.ARTIFACT_EMITTED,
        payload=ArtifactEmittedPayload(
            artifact=TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="answer"),
            artifact_index=1,
        ),
        step_id="generate_answer",
    )
    collector.emit(
        kind=ExecutionEventKind.RUN_COMPLETED,
        payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
    )

    response = present_unified_execution_response(
        UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="answer"),),
            run_id="run-123",
            event_count=3,
            events=collector.events,
            metadata=UseCaseMetadata(artifact_kinds_returned=("text",), artifact_count=1),
        )
    )
    presenters_module.load_projected_sources = original_loader

    assert response.run_id == "run-123"
    assert response.events is not None
    assert response.events[1].kind == "artifact_emitted"
    assert response.events[1].payload["artifact"]["content"]["text"] == "answer"


def test_present_unified_execution_response_projects_participating_sources() -> None:
    original_loader = presenters_module.load_projected_sources
    presenters_module.load_projected_sources = lambda participating_doc_ids: (
        SourceCatalogEntry(
            doc_id="d1",
            source="kb/a.md",
            source_type="file",
            title="Doc A",
            chunk_count=2,
            participation_state=SourceParticipationState.PARTICIPATING,
        ),
        SourceCatalogEntry(
            doc_id="d2",
            source="kb/b.md",
            source_type="file",
            title="Doc B",
            chunk_count=1,
            participation_state=SourceParticipationState.INDEXED,
        ),
    )

    response = present_unified_execution_response(
        UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(),
            citations=(
                CitationRecord(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="alpha"),
            ),
            metadata=UseCaseMetadata(),
        )
    )
    presenters_module.load_projected_sources = original_loader

    assert [item.doc_id for item in response.participating_sources] == ["d1", "d2"]
    assert response.participating_sources[0].participation_state == "participating"
    assert response.participating_sources[1].participation_state == "indexed"


def test_present_unified_execution_response_keeps_participating_sources_stable_without_citations() -> None:
    original_loader = presenters_module.load_projected_sources
    presenters_module.load_projected_sources = lambda participating_doc_ids: ()

    response = present_unified_execution_response(
        UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(),
            citations=(),
            metadata=UseCaseMetadata(),
        )
    )
    presenters_module.load_projected_sources = original_loader

    assert response.participating_sources == []
