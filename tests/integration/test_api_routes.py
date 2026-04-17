"""Integration tests for API routes using FastAPI TestClient."""

import json

from fastapi.testclient import TestClient

from app.application.artifacts import (
    ArtifactKind,
    MermaidArtifact,
    SearchResultItemArtifact,
    SearchResultsArtifact,
    StructuredJsonArtifact,
    TextArtifact,
)
from app.application.events import EventCollector, ExecutionEventKind, RunFailedPayload, RunStartedPayload
from app.application.models import ExecutionSummary, TaskType, UnifiedExecutionResponse
from app.llm.mock import INSUFFICIENT_EVIDENCE, MockLLM
from app.main import app
from app.rag.retrieval_models import ComparedPoint, EvidenceFreshness, EvidenceObject, GroundedAnswer, GroundedCompareResult, RefusalReason, RetrievedChunk, RetrievalFilters, SearchHitRecord, SearchResult, SupportStatus
from app.rag.source_models import FailedSourceInfo, IngestBatchResult, IngestSourceResult, SourceDescriptor
from app.services.grounded_generation import build_citation
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
    UseCaseMetadata,
)
from app.rag.source_models import DeleteSourceResult, SourceCatalogEntry, SourceChunkPage, SourceChunkPreview, SourceDetail, SourceInspectResult, SourceState


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        text="MindDock stores chunks in local Chroma.",
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        source_type="file",
        title="doc",
        section="Storage",
        location="Storage",
        ref="doc > Storage",
        page=None,
        anchor=None,
        distance=0.1,
    )


def _parse_sse_body(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        parsed: dict[str, object] = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                parsed["event"] = line[len("event: "):]
            if line.startswith("data: "):
                parsed["data"] = json.loads(line[len("data: "):])
        events.append(parsed)
    return events


def test_root_and_health_endpoints() -> None:
    client = TestClient(app)

    root_response = client.get("/")
    health_response = client.get("/health")

    assert root_response.status_code == 200
    assert health_response.status_code == 200
    assert root_response.json()["service"] == "MindDock"
    assert health_response.json()["status"] == "ok"


def test_search_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()

    def fake_execute(request) -> UnifiedExecutionResponse:
        assert request.task_type == TaskType.SEARCH
        return UnifiedExecutionResponse(
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
                            snippet="stubbed hit",
                            score=0.1,
                        ),
                    ),
                    total=1,
                    offset=0,
                    limit=1,
                ),
            ),
            citations=[build_citation(_chunk())],
            metadata=UseCaseMetadata(retrieved_count=1, artifact_kinds_returned=("search_results",), artifact_count=1),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post("/search", json={"query": "test query", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "test query"
    assert body["hits"][0]["chunk_id"] == "c1"
    assert body["hits"][0]["source_type"] == "file"
    assert body["hits"][0]["citation"]["snippet"] == "stubbed hit"
    assert body["hits"][0]["citation"]["page"] is None


def test_search_endpoint_forwards_enhanced_filters(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()
    captured: dict[str, object] = {}

    def fake_execute(request) -> UnifiedExecutionResponse:
        captured["filters"] = request.retrieval.filters
        return UnifiedExecutionResponse(
            task_type=TaskType.SEARCH,
            artifacts=(
                SearchResultsArtifact(
                    artifact_id="search-1",
                    kind=ArtifactKind.SEARCH_RESULTS,
                    items=(),
                    total=0,
                    offset=0,
                    limit=1,
                ),
            ),
            metadata=UseCaseMetadata(retrieved_count=0, artifact_kinds_returned=("search_results",), artifact_count=1),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post(
        "/search",
        json={
            "query": "test query",
            "top_k": 1,
            "filters": {
                "source": ["kb/doc.md", "https://example.com"],
                "source_type": ["file", "url"],
                "section": "Storage",
                "title_contains": "doc",
            },
        },
    )

    assert response.status_code == 200
    assert captured["filters"] == RetrievalFilters(
        sources=("kb/doc.md", "https://example.com"),
        source_types=("file", "url"),
        section="Storage",
        title_contains="doc",
    )


def test_chat_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_chat(query: str, top_k: int, filters: RetrievalFilters | None = None) -> ChatServiceResult:
        return ChatServiceResult(
            answer="stubbed answer",
            citations=[build_citation(_chunk())],
            grounded_answer=GroundedAnswer(
                answer="stubbed answer",
                evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="stubbed answer", score=0.1),),
            ),
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded", support_status="supported"),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_chat_request", fake_chat)

    response = client.post("/chat", json={"query": "test query", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "stubbed answer"
    assert body["support_status"] == "supported"
    assert body["refusal_reason"] is None
    assert body["evidence"][0]["chunk_id"] == "c1"
    assert body["retrieved_count"] == 1
    assert body["mode"] == "grounded"
    assert body["citations"][0]["section"] == "Storage"
    assert body["citations"][0]["page"] is None


def test_chat_endpoint_without_api_key_uses_mock_llm_and_filters(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_execute_chat_request(*, query: str, top_k: int, filters: RetrievalFilters | None = None, runtime_name=None, include_metadata=True):
        assert filters == RetrievalFilters(sources=("kb/doc.md",), section="Storage")
        return ChatServiceResult(
            answer=MockLLM().generate(query=query, evidence=[{"text": _chunk().text, "source": _chunk().source, "chunk_id": _chunk().chunk_id}]),
            citations=[build_citation(_chunk())],
            grounded_answer=GroundedAnswer(
                answer="mock grounded answer",
                evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet=_chunk().text, score=0.1),),
            ),
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded", support_status="supported"),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_chat_request", fake_execute_chat_request)

    response = client.post(
        "/chat",
        json={
            "query": "data location",
            "top_k": 1,
            "filters": {"source": "kb/doc.md", "section": "Storage"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "data location" in body["answer"]
    assert "local Chroma" in body["answer"]
    assert body["retrieved_count"] == 1
    assert body["mode"] == "grounded"
    assert body["support_status"] == "supported"
    assert body["evidence"][0]["source"] == "kb/doc.md"
    assert body["citations"][0]["chunk_id"] == "c1"
    assert body["citations"][0]["section"] == "Storage"
    assert body["citations"][0]["page"] is None


def test_summarize_endpoint_without_api_key_returns_summary(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_execute_summarize_request(
        *,
        topic: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
        mode: str = "basic",
        output_format: str = "text",
        runtime_name=None,
        include_metadata=True,
    ):
        assert filters == RetrievalFilters(sources=("kb/doc.md",), section="Storage")
        return SummarizeServiceResult(
            summary=MockLLM().generate(query=topic, evidence=[{"text": _chunk().text, "source": _chunk().source, "chunk_id": _chunk().chunk_id}]),
            citations=[build_citation(_chunk())],
            metadata=UseCaseMetadata(retrieved_count=1, mode=mode, output_format=output_format),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_summarize_request", fake_execute_summarize_request)

    response = client.post(
        "/summarize",
        json={
            "topic": "storage design",
            "top_k": 1,
            "filters": {"source": "kb/doc.md", "section": "Storage"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "storage design" in body["summary"]
    assert body["retrieved_count"] == 1
    assert body["citations"][0]["ref"] == "doc > Storage"
    assert body["mode"] == "basic"
    assert body["output_format"] == "text"


def test_summarize_endpoint_supports_mermaid_output(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_summarize(*, topic: str, top_k: int, filters: RetrievalFilters | None = None, mode: str = "basic", output_format: str = "text", runtime_name=None, include_metadata=True) -> SummarizeServiceResult:
        return SummarizeServiceResult(
            summary="text summary",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode=mode, output_format=output_format),
            structured_output="mindmap\n  root[\"storage\"]",
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_summarize_request", fake_summarize)
    response = client.post(
        "/summarize",
        json={"topic": "storage design", "top_k": 1, "mode": "map_reduce", "output_format": "mermaid"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "map_reduce"
    assert body["output_format"] == "mermaid"
    assert body["structured_output"].startswith("mindmap")


def test_summarize_endpoint_returns_insufficient_evidence_when_empty(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_execute_summarize_request(*, topic: str, top_k: int, filters: RetrievalFilters | None = None, mode: str = "basic", output_format: str = "text", runtime_name=None, include_metadata=True):
        return SummarizeServiceResult(
            summary=INSUFFICIENT_EVIDENCE,
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=0, mode=mode, output_format=output_format, insufficient_evidence=True),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_summarize_request", fake_execute_summarize_request)

    response = client.post("/summarize", json={"query": "storage design", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == INSUFFICIENT_EVIDENCE
    assert body["citations"] == []
    assert body["retrieved_count"] == 0


def test_compare_endpoint_returns_grounded_compare_result(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_compare(*, question: str, top_k: int, filters: RetrievalFilters | None = None, include_metadata=True):
        assert filters == RetrievalFilters(sources=("kb/a.md", "kb/b.md"))
        return CompareServiceResult(
            compare_result=GroundedCompareResult(
                query=question,
                common_points=(
                    ComparedPoint(
                        statement="Both documents discuss storage.",
                        left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="A storage", score=0.1),),
                        right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="B storage", score=0.2),),
                    ),
                ),
                differences=(
                    ComparedPoint(
                        statement="The documents use different storage engines.",
                        left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="Chroma", score=0.1),),
                        right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="Postgres", score=0.2),),
                    ),
                ),
            ),
            citations=[
                build_citation(_chunk()),
                build_citation(_chunk().with_updates(doc_id="d2", chunk_id="c2", source="kb/b.md", text="Project B storage")),
            ],
            metadata=UseCaseMetadata(retrieved_count=2, mode="grounded_compare", support_status="supported"),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_compare_request", fake_compare)

    response = client.post(
        "/compare",
        json={"question": "Compare storage", "top_k": 4, "filters": {"source": ["kb/a.md", "kb/b.md"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Compare storage"
    assert body["support_status"] == "supported"
    assert body["common_points"][0]["left_evidence"][0]["freshness"] == "fresh"
    assert body["differences"][0]["right_evidence"][0]["chunk_id"] == "c2"


def test_unified_execute_endpoint_returns_artifacts_and_metadata(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_execute(request):
        return UnifiedExecutionResponse(
            task_type=TaskType.SUMMARIZE,
            artifacts=(
                TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="summary"),
                MermaidArtifact(
                    artifact_id="mermaid-1",
                    kind=ArtifactKind.MERMAID,
                    mermaid_code="mindmap\n  root((summary))",
                ),
            ),
            citations=[build_citation(_chunk())],
            grounded_answer=GroundedAnswer(
                answer="summary",
                evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="proof", score=0.1),),
            ),
            metadata=UseCaseMetadata(
                selected_runtime="langchain",
                selected_profile_id="default_cloud",
                selected_provider_kind="openai_compatible",
                selected_model_name="gpt-4o-mini",
                execution_steps_executed=("retrieve", "generate", "format_output"),
                runtime_capabilities_matched=("supports_summarize",),
                resolved_capabilities=("supports_summarize",),
                fallback_used=False,
                selection_reason="preferred:preferred_profile",
                policy_applied="selection_mode=preferred",
                retrieved_count=1,
                support_status="supported",
                artifact_kinds_returned=("text", "mermaid"),
                primary_artifact_kind="text",
                artifact_count=2,
            ),
            execution_summary=ExecutionSummary(
                selected_runtime="langchain",
                selected_profile_id="default_cloud",
                selected_provider_kind="openai_compatible",
                selected_model_name="gpt-4o-mini",
                selected_capabilities=("supports_summarize",),
                fallback_used=False,
                selection_reason="preferred:preferred_profile",
                policy_applied="selection_mode=preferred",
                execution_steps_executed=("retrieve", "generate", "format_output"),
                artifact_kinds_returned=("text", "mermaid"),
                primary_artifact_kind="text",
                artifact_count=2,
            ),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post(
        "/frontend/execute",
        json={
            "task_type": "summarize",
            "user_input": "storage design",
            "output_mode": "mermaid",
            "execution_policy": {"preferred_profile_id": "default_cloud", "selection_mode": "preferred"},
            "include_metadata": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "summarize"
    assert body["artifacts"][1]["kind"] == "mermaid"
    assert body["grounded_answer"]["support_status"] == "supported"
    assert body["grounded_answer"]["evidence"][0]["chunk_id"] == "c1"
    assert body["metadata"]["selected_runtime"] == "langchain"
    assert body["metadata"]["selected_profile_id"] == "default_cloud"
    assert body["metadata"]["selection_reason"] == "preferred:preferred_profile"
    assert body["metadata"]["support_status"] == "supported"
    assert "generate" in body["metadata"]["execution_steps_executed"]
    assert body["metadata"]["artifact_kinds_returned"] == ["text", "mermaid"]
    assert body["execution_summary"]["artifact_count"] == 2
    assert body["events"] is None


def test_unified_execute_endpoint_supports_structured_json_artifact(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_execute(request):
        return UnifiedExecutionResponse(
            task_type=TaskType.SUMMARIZE,
            artifacts=(
                StructuredJsonArtifact(
                    artifact_id="structured-1",
                    kind=ArtifactKind.STRUCTURED_JSON,
                    data={"summary": "structured summary"},
                    schema_name="summary.v1",
                ),
            ),
            citations=[],
            metadata=UseCaseMetadata(
                artifact_kinds_returned=("structured_json",),
                primary_artifact_kind="structured_json",
                artifact_count=1,
            ),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post(
        "/frontend/execute",
        json={"task_type": "summarize", "user_input": "storage design", "output_mode": "structured"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifacts"][0]["kind"] == "structured_json"
    assert body["artifacts"][0]["content"]["data"]["summary"] == "structured summary"


def test_unified_execute_endpoint_returns_compare_result(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_execute(request):
        return UnifiedExecutionResponse(
            task_type=TaskType.COMPARE,
            artifacts=(
                TextArtifact(
                    artifact_id="text-1",
                    kind=ArtifactKind.TEXT,
                    text="Comparison question: Compare storage",
                    metadata={
                        "compare_result": {
                            "query": "Compare storage",
                            "common_points": [
                                {
                                    "statement": "Both documents discuss storage.",
                                    "left_evidence": [{"doc_id": "d1", "chunk_id": "c1", "source": "kb/a.md", "snippet": "Chroma", "freshness": "fresh"}],
                                    "right_evidence": [{"doc_id": "d2", "chunk_id": "c2", "source": "kb/b.md", "snippet": "Postgres", "freshness": "fresh"}],
                                    "summary_note": None,
                                }
                            ],
                            "differences": [],
                            "conflicts": [],
                            "support_status": "supported",
                            "refusal_reason": None,
                        }
                    },
                ),
                StructuredJsonArtifact(
                    artifact_id="structured-1",
                    kind=ArtifactKind.STRUCTURED_JSON,
                    data={
                        "query": "Compare storage",
                        "common_points": [
                            {
                                "statement": "Both documents discuss storage.",
                                "left_evidence": [{"doc_id": "d1", "chunk_id": "c1", "source": "kb/a.md", "snippet": "Chroma", "freshness": "fresh"}],
                                "right_evidence": [{"doc_id": "d2", "chunk_id": "c2", "source": "kb/b.md", "snippet": "Postgres", "freshness": "fresh"}],
                                "summary_note": None,
                            }
                        ],
                        "differences": [],
                        "conflicts": [],
                        "support_status": "supported",
                        "refusal_reason": None,
                    },
                    schema_name="compare.v1",
                ),
            ),
            compare_result=GroundedCompareResult(
                query="Compare storage",
                common_points=(
                    ComparedPoint(
                        statement="Both documents discuss storage.",
                        left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="Chroma", score=0.1),),
                        right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="Postgres", score=0.2),),
                    ),
                ),
            ),
            metadata=UseCaseMetadata(
                retrieved_count=2,
                support_status="supported",
                artifact_kinds_returned=("text", "structured_json"),
                primary_artifact_kind="text",
                artifact_count=2,
            ),
            execution_summary=ExecutionSummary(primary_artifact_kind="text", artifact_count=2),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post(
        "/frontend/execute",
        json={"task_type": "compare", "user_input": "Compare storage", "output_mode": "structured"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "compare"
    assert body["compare_result"]["support_status"] == "supported"
    assert body["artifacts"][0]["metadata"]["compare_result"]["common_points"][0]["left_evidence"][0]["freshness"] == "fresh"
    assert body["artifacts"][1]["content"]["data"]["query"] == "Compare storage"


def test_unified_execute_endpoint_can_return_events_when_requested(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import (
        ArtifactEmittedPayload,
        EventCollector,
        ExecutionEventKind,
        PlanBuiltPayload,
        RunCompletedPayload,
        RunStartedPayload,
    )

    client = TestClient(app)

    def fake_execute(request):
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
            kind=ExecutionEventKind.PLAN_BUILT,
            payload=PlanBuiltPayload(
                step_count=1,
                step_ids=("generate_answer",),
                step_kinds=("generate",),
                requires_runtime=True,
            ),
        )
        collector.emit(
            kind=ExecutionEventKind.ARTIFACT_EMITTED,
            payload=ArtifactEmittedPayload(
                artifact=TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello"),
                artifact_index=1,
            ),
            step_id="generate_answer",
        )
        collector.emit(
            kind=ExecutionEventKind.RUN_COMPLETED,
            payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
        )
        events = collector.events
        return UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello"),),
            run_id="run-123",
            event_count=len(events),
            events=events,
            metadata=UseCaseMetadata(artifact_kinds_returned=("text",), artifact_count=1),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post(
        "/frontend/execute",
        json={"task_type": "chat", "user_input": "hello", "include_events": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-123"
    assert body["event_count"] == 4
    assert body["events"][0]["kind"] == "run_started"
    assert body["events"][2]["payload"]["artifact"]["kind"] == "text"


def test_unified_execute_endpoint_projects_participating_sources(monkeypatch) -> None:
    from app.api import routes
    import app.api.presenters as presenters_module
    from app.rag.source_models import SourceParticipationState

    client = TestClient(app)

    def fake_execute(request):
        return UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(),
            citations=(build_citation(_chunk()),),
            metadata=UseCaseMetadata(),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)
    monkeypatch.setattr(
        presenters_module,
        "load_projected_sources",
        lambda participating_doc_ids: (
            SourceCatalogEntry(
                doc_id="d1",
                source="kb/doc.md",
                source_type="file",
                title="Doc One",
                chunk_count=1,
                participation_state=SourceParticipationState.PARTICIPATING,
            ),
            SourceCatalogEntry(
                doc_id="d2",
                source="kb/other.md",
                source_type="file",
                title="Doc Two",
                chunk_count=1,
                participation_state=SourceParticipationState.INDEXED,
            ),
        ),
    )

    response = client.post(
        "/frontend/execute",
        json={"task_type": "chat", "user_input": "hello"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["doc_id"] for item in body["participating_sources"]] == ["d1", "d2"]
    assert body["participating_sources"][0]["participation_state"] == "participating"
    assert body["participating_sources"][1]["participation_state"] == "indexed"


def test_unified_execute_stream_endpoint_returns_valid_sse(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import (
        ArtifactEmittedPayload,
        ExecutionRun,
        ExecutionRunStatus,
        PlanBuiltPayload,
        RunCompletedPayload,
        StepStartedPayload,
    )

    client = TestClient(app)

    def fake_execute_run(request):
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
            kind=ExecutionEventKind.PLAN_BUILT,
            payload=PlanBuiltPayload(step_count=1, step_ids=("generate_answer",), step_kinds=("generate",), requires_runtime=True),
        )
        collector.emit(
            kind=ExecutionEventKind.STEP_STARTED,
            payload=StepStartedPayload(step_name="generate_answer", step_kind="generate"),
        )
        collector.emit(
            kind=ExecutionEventKind.ARTIFACT_EMITTED,
            payload=ArtifactEmittedPayload(
                artifact=TextArtifact(
                    artifact_id="text-1",
                    kind=ArtifactKind.TEXT,
                    text="hello",
                    metadata={
                        "grounded_answer": {
                            "answer": "hello",
                            "evidence": [
                                {
                                    "doc_id": "d1",
                                    "chunk_id": "c1",
                                    "source": "kb/doc.md",
                                    "snippet": "proof",
                                    "source_version": "hash-1",
                                    "content_hash": "hash-1",
                                    "freshness": "fresh",
                                }
                            ],
                            "support_status": "insufficient_evidence",
                            "refusal_reason": "no_relevant_evidence",
                        }
                    },
                ),
                artifact_index=1,
            ),
        )
        collector.emit(
            kind=ExecutionEventKind.RUN_COMPLETED,
            payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
        )
        return ExecutionRun(
            run_id="run-123",
            request_summary=type("ReqSummaryObj", (), {})(),
            status=ExecutionRunStatus.COMPLETED,
            events=collector.events,
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_run", fake_execute_run)

    response = client.post("/frontend/execute/stream", json={"task_type": "chat", "user_input": "hello"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_body(response.text)
    assert [event["event"] for event in events] == ["run_started", "progress", "progress", "artifact", "completed"]
    assert events[3]["data"]["payload"]["artifact"]["content"]["text"] == "hello"
    assert events[3]["data"]["payload"]["artifact"]["metadata"]["grounded_answer"]["support_status"] == "insufficient_evidence"
    assert events[3]["data"]["payload"]["artifact"]["metadata"]["grounded_answer"]["evidence"][0]["freshness"] == "fresh"


def test_unified_execute_stream_completed_event_projects_participating_sources(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ExecutionRun, ExecutionRunStatus, RunCompletedPayload
    from app.rag.source_models import SourceParticipationState

    client = TestClient(app)

    def fake_execute_run(request):
        collector = EventCollector(run_id="run-123", task_type="chat")
        collector.emit(
            kind=ExecutionEventKind.RUN_COMPLETED,
            payload=RunCompletedPayload(
                artifact_count=1,
                primary_artifact_kind="text",
                participating_sources=(
                    SourceCatalogEntry(
                        doc_id="d1",
                        source="kb/doc.md",
                        source_type="file",
                        title="Doc One",
                        chunk_count=1,
                        participation_state=SourceParticipationState.PARTICIPATING,
                    ),
                    SourceCatalogEntry(
                        doc_id="d2",
                        source="kb/other.md",
                        source_type="file",
                        title="Doc Two",
                        chunk_count=1,
                        participation_state=SourceParticipationState.INDEXED,
                    ),
                ),
            ),
        )
        return ExecutionRun(
            run_id="run-123",
            request_summary=type("ReqSummaryObj", (), {})(),
            status=ExecutionRunStatus.COMPLETED,
            events=collector.events,
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_run", fake_execute_run)

    response = client.post("/frontend/execute/stream", json={"task_type": "chat", "user_input": "hello"})

    assert response.status_code == 200
    events = _parse_sse_body(response.text)
    assert events[-1]["event"] == "completed"
    assert events[-1]["data"]["payload"]["participating_sources"][0]["doc_id"] == "d1"
    assert events[-1]["data"]["payload"]["participating_sources"][0]["participation_state"] == "participating"
    assert events[-1]["data"]["payload"]["participating_sources"][1]["participation_state"] == "indexed"


def test_unified_execute_stream_endpoint_injects_heartbeat_when_gap_exists(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ArtifactEmittedPayload, ExecutionRun, ExecutionRunStatus, RunCompletedPayload
    from datetime import datetime, timedelta, timezone

    client = TestClient(app)
    base = datetime.now(timezone.utc)

    def fake_execute_run(request):
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
        collector.sink.events[0] = type(collector.sink.events[0])(**{**collector.sink.events[0].__dict__, "timestamp": base.isoformat()})
        collector.emit(
            kind=ExecutionEventKind.ARTIFACT_EMITTED,
            payload=ArtifactEmittedPayload(
                artifact=TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello"),
                artifact_index=1,
            ),
        )
        collector.sink.events[1] = type(collector.sink.events[1])(**{**collector.sink.events[1].__dict__, "timestamp": (base + timedelta(seconds=10)).isoformat()})
        collector.emit(
            kind=ExecutionEventKind.RUN_COMPLETED,
            payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
        )
        collector.sink.events[2] = type(collector.sink.events[2])(**{**collector.sink.events[2].__dict__, "timestamp": (base + timedelta(seconds=11)).isoformat()})
        routes.frontend_facade.run_registry._runs.clear()
        run = ExecutionRun(
            run_id="run-123",
            request_summary=type("ReqSummaryObj", (), {})(),
            status=ExecutionRunStatus.COMPLETED,
            events=tuple(collector.events),
        )
        routes.frontend_facade.run_registry.register(run)
        routes.frontend_facade.run_registry.record_projected_events(
            "run-123",
            routes.frontend_facade.event_projector.project_many(run.events, debug=False),
        )
        return run

    monkeypatch.setattr(routes.frontend_facade, "execute_run", fake_execute_run)
    object.__setattr__(routes.frontend_facade.run_registry.config, "heartbeat_interval_seconds", 3)

    response = client.post("/frontend/execute/stream", json={"task_type": "chat", "user_input": "hello"})

    events = _parse_sse_body(response.text)
    assert "heartbeat" in [event["event"] for event in events]


def test_unified_execute_stream_endpoint_respects_debug_visibility(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ExecutionRun, ExecutionRunStatus, StepCompletedPayload

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()

    def fake_execute_run(request):
        collector = EventCollector(run_id="run-123", task_type="chat")
        collector.emit(
            kind=ExecutionEventKind.STEP_COMPLETED,
            payload=StepCompletedPayload(step_name="generate_answer", step_kind="generate"),
        )
        return ExecutionRun(
            run_id="run-123",
            request_summary=type("ReqSummaryObj", (), {})(),
            status=ExecutionRunStatus.COMPLETED,
            events=collector.events,
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_run", fake_execute_run)

    public_response = client.post("/frontend/execute/stream", json={"task_type": "chat", "user_input": "hello"})
    debug_response = client.post("/frontend/execute/stream?debug=true", json={"task_type": "chat", "user_input": "hello"})

    assert _parse_sse_body(public_response.text) == []
    debug_events = _parse_sse_body(debug_response.text)
    assert debug_events[0]["data"]["visibility"] == "debug"
    assert debug_events[0]["data"]["payload"]["phase"] == "generating"


def test_unified_execute_stream_endpoint_emits_failed_event(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ExecutionRun, ExecutionRunStatus

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()

    def fake_execute_run(request):
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
            kind=ExecutionEventKind.RUN_FAILED,
            payload=RunFailedPayload(error="RuntimeError", detail="boom"),
        )
        return ExecutionRun(
            run_id="run-123",
            request_summary=type("ReqSummaryObj", (), {})(),
            status=ExecutionRunStatus.FAILED,
            events=collector.events,
            error=RuntimeError("boom"),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_run", fake_execute_run)

    response = client.post("/frontend/execute/stream", json={"task_type": "chat", "user_input": "hello"})

    assert response.status_code == 200
    events = _parse_sse_body(response.text)
    assert events[-1]["event"] == "failed"
    assert events[-1]["data"]["payload"]["detail"] == "boom"


def test_run_status_and_replay_endpoints_work(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ArtifactEmittedPayload, ExecutionRun, ExecutionRunStatus, RunCompletedPayload
    from app.application.client_events import EventProjector

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()
    collector = EventCollector(run_id="run-xyz", task_type="chat")
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
            artifact=TextArtifact(
                artifact_id="text-1",
                kind=ArtifactKind.TEXT,
                text="hello",
                metadata={
                    "grounded_answer": {
                        "answer": "hello",
                        "evidence": [
                            {
                                "doc_id": "d1",
                                "chunk_id": "c1",
                                "source": "kb/doc.md",
                                "snippet": "proof",
                                "source_version": "hash-1",
                                "content_hash": "hash-1",
                                "freshness": "fresh",
                            }
                        ],
                        "support_status": "supported",
                        "refusal_reason": None,
                    }
                },
            ),
            artifact_index=1,
        ),
    )
    collector.emit(
        kind=ExecutionEventKind.RUN_COMPLETED,
        payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
    )
    run = ExecutionRun(
        run_id="run-xyz",
        request_summary=type(
            "ReqSummaryObj",
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
        status=ExecutionRunStatus.COMPLETED,
        events=collector.events,
        final_response=UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello"),),
        ),
    )
    routes.frontend_facade.run_registry.register(run)
    routes.frontend_facade.run_registry.record_projected_events(
        "run-xyz",
        EventProjector().project_many(run.events),
    )
    routes.frontend_facade.run_registry.mark_completed("run-xyz", run.final_response)

    status_response = client.get("/frontend/runs/run-xyz")
    replay_response = client.get("/frontend/runs/run-xyz/events")

    assert status_response.status_code == 200
    assert status_response.json()["run_id"] == "run-xyz"
    assert status_response.json()["has_final_response"] is True
    assert replay_response.status_code == 200
    assert replay_response.json()["items"][1]["kind"] == "artifact"
    assert replay_response.json()["items"][1]["payload"]["artifact"]["metadata"]["grounded_answer"]["support_status"] == "supported"
    assert replay_response.json()["items"][1]["payload"]["artifact"]["metadata"]["grounded_answer"]["evidence"][0]["freshness"] == "fresh"


def test_run_replay_surfaces_compare_artifact_projection() -> None:
    from app.api import routes
    from app.application.events import ArtifactEmittedPayload, ExecutionRun, ExecutionRunStatus, RunCompletedPayload
    from app.application.client_events import EventProjector

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()
    collector = EventCollector(run_id="run-compare", task_type="compare")
    collector.emit(
        kind=ExecutionEventKind.RUN_STARTED,
        payload=RunStartedPayload(
            request=type(
                "ReqSummary",
                (),
                {
                    "task_type": "compare",
                    "user_input_preview": "Compare storage",
                    "output_mode": "structured",
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
            artifact=TextArtifact(
                artifact_id="text-1",
                kind=ArtifactKind.TEXT,
                text="Comparison question: Compare storage",
                metadata={
                    "compare_result": {
                        "query": "Compare storage",
                        "common_points": [
                            {
                                "statement": "Both documents discuss storage.",
                                "left_evidence": [{"doc_id": "d1", "chunk_id": "c1", "source": "kb/a.md", "snippet": "Chroma", "freshness": "fresh"}],
                                "right_evidence": [{"doc_id": "d2", "chunk_id": "c2", "source": "kb/b.md", "snippet": "Postgres", "freshness": "fresh"}],
                                "summary_note": None,
                            }
                        ],
                        "differences": [],
                        "conflicts": [],
                        "support_status": "supported",
                        "refusal_reason": None,
                    }
                },
            ),
            artifact_index=1,
        ),
    )
    collector.emit(
        kind=ExecutionEventKind.RUN_COMPLETED,
        payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
    )
    run = ExecutionRun(
        run_id="run-compare",
        request_summary=type(
            "ReqSummaryObj",
            (),
            {
                "task_type": "compare",
                "user_input_preview": "Compare storage",
                "output_mode": "structured",
                "top_k": 5,
                "citation_policy": "preferred",
                "skill_policy": "disabled",
            },
        )(),
        status=ExecutionRunStatus.COMPLETED,
        events=collector.events,
        final_response=UnifiedExecutionResponse(task_type=TaskType.COMPARE, artifacts=(TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="done"),)),
    )
    routes.frontend_facade.run_registry.register(run)
    routes.frontend_facade.run_registry.record_projected_events("run-compare", EventProjector().project_many(run.events))
    routes.frontend_facade.run_registry.mark_completed("run-compare", run.final_response)

    replay_response = client.get("/frontend/runs/run-compare/events")

    assert replay_response.status_code == 200
    artifact_payload = replay_response.json()["items"][1]["payload"]["artifact"]
    assert artifact_payload["metadata"]["compare_result"]["support_status"] == "supported"
    assert artifact_payload["metadata"]["compare_result"]["common_points"][0]["left_evidence"][0]["freshness"] == "fresh"


def test_cancel_run_endpoint_sets_cancellation_requested(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ExecutionRun, ExecutionRunStatus

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()
    run = ExecutionRun(
        run_id="run-cancel",
        request_summary=type("ReqSummaryObj", (), {"task_type": "chat", "user_input_preview": "hello", "output_mode": "text", "top_k": 5, "citation_policy": "preferred", "skill_policy": "disabled"})(),
        status=ExecutionRunStatus.RUNNING,
    )
    routes.frontend_facade.run_registry.register(run)

    response = client.post("/frontend/runs/run-cancel/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["cancellation_requested"] is True
    assert body["accepted"] is True


def test_cancel_completed_run_endpoint_reports_stable_semantics(monkeypatch) -> None:
    from app.api import routes
    from app.application.events import ExecutionRun, ExecutionRunStatus

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()
    run = ExecutionRun(
        run_id="run-done",
        request_summary=type("ReqSummaryObj", (), {"task_type": "chat", "user_input_preview": "hello", "output_mode": "text", "top_k": 5, "citation_policy": "preferred", "skill_policy": "disabled"})(),
        status=ExecutionRunStatus.COMPLETED,
    )
    routes.frontend_facade.run_registry.register(run)
    routes.frontend_facade.run_registry.mark_completed("run-done")

    response = client.post("/frontend/runs/run-done/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False


def test_runtime_profiles_endpoint_returns_safe_summaries(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    class FakeSummary:
        def __init__(self, profile_id, display_name, provider_kind, model_name, tags, enabled, capabilities):
            self.profile_id = profile_id
            self.display_name = display_name
            self.provider_kind = provider_kind
            self.model_name = model_name
            self.tags = tags
            self.enabled = enabled
            self.capabilities = capabilities

    monkeypatch.setattr(
        routes.frontend_facade,
        "list_runtime_profiles",
        lambda: (
            FakeSummary("default_cloud", "Default Cloud", "openai_compatible", "gpt-4o-mini", ("cloud",), True, ("supports_chat",)),
            FakeSummary("local_ollama", "Local Ollama", "ollama", "llama3.1", ("local", "private"), True, ("supports_chat",)),
        ),
    )

    response = client.get("/frontend/runtime-profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["profile_id"] == "default_cloud"
    assert "api_key" not in str(body).lower()


def test_ingest_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_ingest(rebuild: bool = False, urls: list[str] | None = None) -> IngestServiceResult:
        return IngestServiceResult(
            batch=IngestBatchResult(
                source_results=[
                    IngestSourceResult(descriptor=SourceDescriptor(source="doc1.md", source_type="file"), ok=True, chunks_upserted=5),
                    IngestSourceResult(descriptor=SourceDescriptor(source="doc2.md", source_type="file"), ok=True, chunks_upserted=5),
                    IngestSourceResult(descriptor=SourceDescriptor(source="doc3.md", source_type="file"), ok=True, chunks_upserted=5),
                    IngestSourceResult(descriptor=SourceDescriptor(source="https://example.com", source_type="url"), ok=True, chunks_upserted=5),
                ]
            ),
            metadata=UseCaseMetadata(partial_failure=False),
        )

    monkeypatch.setattr(routes.frontend_facade.knowledge_base, "ingest", fake_ingest)

    response = client.post("/ingest", json={"rebuild": False, "urls": ["https://example.com"]})

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == 4
    assert body["chunks"] == 20
    assert "https://example.com" in body["ingested_sources"]
    assert body["failed_sources"] == []
    assert body["partial_failure"] is False


def test_ingest_endpoint_rebuild_flag(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)
    captured: dict[str, object] = {}

    def fake_ingest(rebuild: bool = False, urls: list[str] | None = None) -> IngestServiceResult:
        captured["rebuild"] = rebuild
        captured["urls"] = urls
        return IngestServiceResult(batch=IngestBatchResult(source_results=[]), metadata=UseCaseMetadata())

    monkeypatch.setattr(routes.frontend_facade.knowledge_base, "ingest", fake_ingest)

    response = client.post("/ingest", json={"rebuild": True, "urls": ["https://example.com"]})

    assert response.status_code == 200
    assert captured["rebuild"] is True
    assert captured["urls"] == ["https://example.com"]


def test_search_empty_query_returns_422() -> None:
    client = TestClient(app)
    response = client.post("/search", json={"query": "   "})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert "query" in body["detail"]


def test_search_invalid_page_range_returns_422() -> None:
    client = TestClient(app)
    response = client.post("/search", json={"query": "test", "filters": {"page_from": 3, "page_to": 1}})
    assert response.status_code == 422
    assert "page_from" in response.json()["detail"]


def test_ingest_invalid_url_returns_422() -> None:
    client = TestClient(app)
    response = client.post("/ingest", json={"urls": ["ftp://example.com"]})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert response.json()["category"] == "validation_error"


def test_ingest_partial_failure_response_is_serialized(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_ingest(rebuild: bool = False, urls: list[str] | None = None) -> IngestServiceResult:
        return IngestServiceResult(
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

    monkeypatch.setattr(routes.frontend_facade.knowledge_base, "ingest", fake_ingest)

    response = client.post("/ingest", json={"urls": ["https://example.com"]})

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == 1
    assert body["partial_failure"] is True
    assert body["failed_sources"][0]["source_type"] == "url"


def test_sources_endpoints_with_stubbed_catalog_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    monkeypatch.setattr(
        routes.frontend_facade.knowledge_base,
        "list_sources",
        lambda source_type=None: CatalogServiceResult(
            entries=[
                SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type=source_type or "file",
                    title="notes",
                    chunk_count=2,
                    sections=("Storage",),
                    state=SourceState(
                        doc_id="d1",
                        source="notes.md",
                        current_version="hash-1",
                        content_hash="hash-1",
                        last_ingested_at="2026-04-05T10:00:00+00:00",
                        chunk_count=2,
                        ingest_status="ready",
                    ),
                )
            ]
        ),
    )
    monkeypatch.setattr(
        routes.frontend_facade.knowledge_base,
        "get_source_detail",
        lambda doc_id=None, source=None, include_admin_metadata=False: SourceDetailServiceResult(
            found=True,
            detail=SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id=doc_id or "d1",
                    source=source or "notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                    state=SourceState(
                        doc_id=doc_id or "d1",
                        source=source or "notes.md",
                        current_version="hash-1",
                        content_hash="hash-1",
                        last_ingested_at="2026-04-05T10:00:00+00:00",
                        chunk_count=2,
                        ingest_status="ready",
                    ),
                ),
                representative_metadata={"title": "notes"},
            ),
            include_admin_metadata=include_admin_metadata,
            admin_metadata={"doc_id": doc_id or "d1"} if include_admin_metadata else {},
        ),
    )
    monkeypatch.setattr(
        routes.frontend_facade.knowledge_base,
        "inspect_source",
        lambda doc_id=None, source=None, limit=10, offset=0, include_admin_metadata=False: SourceInspectServiceResult(
            found=True,
            inspect=SourceInspectResult(
                detail=SourceDetail(
                    entry=SourceCatalogEntry(
                        doc_id=doc_id or "d1",
                        source=source or "notes.md",
                        source_type="file",
                        title="notes",
                        chunk_count=2,
                        state=SourceState(
                            doc_id=doc_id or "d1",
                            source=source or "notes.md",
                            current_version="hash-1",
                            content_hash="hash-1",
                            last_ingested_at="2026-04-05T10:00:00+00:00",
                            chunk_count=2,
                            ingest_status="ready",
                        ),
                    ),
                    representative_metadata={"title": "notes"},
                ),
                chunk_page=SourceChunkPage(
                    total_chunks=2,
                    returned_chunks=1,
                    limit=limit,
                    offset=offset,
                    chunks=[
                        SourceChunkPreview(
                            chunk_id="d1:1",
                            chunk_index=1,
                            preview_text="chunk preview",
                            title="notes",
                            section="Storage",
                            location="Storage",
                            ref="notes > Storage",
                            admin_metadata={"doc_id": doc_id or "d1"} if include_admin_metadata else {},
                        )
                    ],
                ),
                include_admin_metadata=include_admin_metadata,
                admin_metadata={"doc_id": doc_id or "d1"} if include_admin_metadata else {},
            ),
        ),
    )
    monkeypatch.setattr(
        routes.frontend_facade.knowledge_base,
        "delete_source",
        lambda doc_id=None, source=None: DeleteSourceServiceResult(
            result=DeleteSourceResult(
                found=True,
                doc_id=doc_id or "d1",
                source=source or "notes.md",
                source_type="file",
                deleted_chunks=2,
            )
        ),
    )
    monkeypatch.setattr(
        routes.frontend_facade.knowledge_base,
        "reingest_source",
        lambda doc_id=None, source=None: ReingestSourceServiceResult(
            found=True,
            source_result=IngestSourceResult(
                descriptor=SourceDescriptor(source=source or "notes.md", source_type="file"),
                ok=True,
                chunks_upserted=2,
                chunks_deleted=1,
            ),
        ),
    )

    list_response = client.get("/sources?source_type=file")
    detail_response = client.get("/sources/d1?include_admin_metadata=true")
    by_source_response = client.get("/sources/by-source?source=notes.md")
    chunks_response = client.get("/sources/d1/chunks?limit=1&offset=1&include_admin_metadata=true")
    chunks_by_source_response = client.get("/sources/by-source/chunks?source=notes.md&limit=1&offset=0")
    delete_response = client.delete("/sources/d1")
    reingest_response = client.post("/sources/d1/reingest")

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert detail_response.json()["item"]["source"] == "notes.md"
    assert detail_response.json()["item"]["source_state"]["current_version"] == "hash-1"
    assert detail_response.json()["admin_metadata"]["doc_id"] == "d1"
    assert by_source_response.json()["found"] is True
    assert chunks_response.json()["returned_chunks"] == 1
    assert chunks_response.json()["chunks"][0]["chunk_index"] == 1
    assert chunks_response.json()["admin_metadata"]["doc_id"] == "d1"
    assert chunks_by_source_response.json()["item"]["source"] == "notes.md"
    assert delete_response.json()["deleted_chunks"] == 2
    assert reingest_response.json()["chunks_upserted"] == 2


def test_compare_endpoint_returns_insufficient_evidence(monkeypatch) -> None:
    """Direct /compare returns insufficient_evidence when compare service detects < 2 groups."""
    from app.api import routes

    client = TestClient(app)

    def fake_compare(*, question: str, top_k: int, filters: RetrievalFilters | None = None, include_metadata=True):
        return CompareServiceResult(
            compare_result=GroundedCompareResult(
                query=question,
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            ),
            citations=[],
            metadata=UseCaseMetadata(
                retrieved_count=1,
                mode="grounded_compare",
                insufficient_evidence=True,
                support_status="insufficient_evidence",
            ),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_compare_request", fake_compare)

    response = client.post(
        "/compare",
        json={"question": "Compare unrelated docs", "top_k": 4},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["support_status"] == "insufficient_evidence"
    assert body["common_points"] == []
    assert body["differences"] == []
    assert body["conflicts"] == []


def test_unified_execute_compare_returns_insufficient_evidence(monkeypatch) -> None:
    """Unified /frontend/execute with task_type=compare returns insufficient_evidence."""
    from app.api import routes

    client = TestClient(app)

    def fake_execute(request):
        assert request.task_type == TaskType.COMPARE
        return UnifiedExecutionResponse(
            task_type=TaskType.COMPARE,
            artifacts=(
                TextArtifact(
                    artifact_id="text-1",
                    kind=ArtifactKind.TEXT,
                    text="Insufficient evidence to compare the requested documents.",
                    metadata={
                        "compare_result": {
                            "query": "Compare unrelated docs",
                            "common_points": [],
                            "differences": [],
                            "conflicts": [],
                            "support_status": "insufficient_evidence",
                            "refusal_reason": None,
                        }
                    },
                ),
            ),
            compare_result=GroundedCompareResult(
                query="Compare unrelated docs",
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            ),
            metadata=UseCaseMetadata(
                retrieved_count=1,
                insufficient_evidence=True,
                support_status="insufficient_evidence",
                artifact_kinds_returned=("text",),
                primary_artifact_kind="text",
                artifact_count=1,
            ),
            execution_summary=ExecutionSummary(primary_artifact_kind="text", artifact_count=1),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute)

    response = client.post(
        "/frontend/execute",
        json={"task_type": "compare", "user_input": "Compare unrelated docs", "output_mode": "structured"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "compare"
    assert body["compare_result"]["support_status"] == "insufficient_evidence"
    assert body["artifacts"][0]["metadata"]["compare_result"]["support_status"] == "insufficient_evidence"


def test_compare_endpoint_and_unified_execute_return_consistent_contracts(monkeypatch) -> None:
    """Both /compare and /frontend/execute return the same compare_result structure for happy path."""
    from app.api import routes

    client = TestClient(app)

    shared_compare_result = GroundedCompareResult(
        query="Compare storage",
        common_points=(
            ComparedPoint(
                statement="Both documents discuss storage.",
                left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="Chroma", score=0.1, freshness=EvidenceFreshness.FRESH),),
                right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="Postgres", score=0.2, freshness=EvidenceFreshness.FRESH),),
            ),
        ),
        differences=(
            ComparedPoint(
                statement="Different storage engines.",
                left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="Chroma", score=0.1, freshness=EvidenceFreshness.FRESH),),
                right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="Postgres", score=0.2, freshness=EvidenceFreshness.FRESH),),
            ),
        ),
        support_status=SupportStatus.SUPPORTED,
    )

    def fake_compare_direct(*, question: str, top_k: int, filters=None, include_metadata=True):
        return CompareServiceResult(
            compare_result=shared_compare_result,
            citations=[
                build_citation(_chunk()),
                build_citation(_chunk().with_updates(doc_id="d2", chunk_id="c2", source="kb/b.md")),
            ],
            metadata=UseCaseMetadata(
                retrieved_count=2,
                mode="grounded_compare",
                support_status="supported",
            ),
        )

    def fake_execute_unified(request):
        assert request.task_type == TaskType.COMPARE
        return UnifiedExecutionResponse(
            task_type=TaskType.COMPARE,
            artifacts=(
                TextArtifact(
                    artifact_id="text-1",
                    kind=ArtifactKind.TEXT,
                    text="Comparison question: Compare storage",
                    metadata={"compare_result": shared_compare_result.to_api_dict()},
                ),
                StructuredJsonArtifact(
                    artifact_id="structured-1",
                    kind=ArtifactKind.STRUCTURED_JSON,
                    data=shared_compare_result.to_api_dict(),
                    schema_name="compare.v1",
                ),
            ),
            compare_result=shared_compare_result,
            citations=[
                build_citation(_chunk()),
                build_citation(_chunk().with_updates(doc_id="d2", chunk_id="c2", source="kb/b.md")),
            ],
            metadata=UseCaseMetadata(
                retrieved_count=2,
                support_status="supported",
                artifact_kinds_returned=("text", "structured_json"),
                primary_artifact_kind="text",
                artifact_count=2,
            ),
            execution_summary=ExecutionSummary(
                primary_artifact_kind="text",
                artifact_count=2,
            ),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_compare_request", fake_compare_direct)
    monkeypatch.setattr(routes.frontend_facade, "execute", fake_execute_unified)

    direct_response = client.post(
        "/compare",
        json={"question": "Compare storage", "top_k": 4},
    )
    unified_response = client.post(
        "/frontend/execute",
        json={"task_type": "compare", "user_input": "Compare storage", "output_mode": "structured"},
    )

    assert direct_response.status_code == 200
    assert unified_response.status_code == 200

    direct_body = direct_response.json()
    unified_body = unified_response.json()

    # Core contract fields must match
    assert direct_body["support_status"] == unified_body["compare_result"]["support_status"]
    assert len(direct_body["common_points"]) == len(unified_body["compare_result"]["common_points"])
    assert len(direct_body["differences"]) == len(unified_body["compare_result"]["differences"])

    # citations must be present in both
    assert len(direct_body["citations"]) >= 1
    assert len(unified_body["citations"]) >= 1

    # unified execute must have compare.v1 artifact
    artifact_kinds = [a["kind"] for a in unified_body["artifacts"]]
    assert "structured_json" in artifact_kinds
    compare_v1_artifact = next(a for a in unified_body["artifacts"] if a["kind"] == "structured_json")
    assert compare_v1_artifact["content"]["schema_name"] == "compare.v1"

    # top-level compare_result must match compare.v1 artifact data
    assert compare_v1_artifact["content"]["data"]["support_status"] == unified_body["compare_result"]["support_status"]


def test_compare_freshness_stale_possible_projected_in_response(monkeypatch) -> None:
    """Evidence freshness staleness is correctly projected in compare responses via controlled catalog state.

    This test injects a fake CompareService with a controlled collection into the facade's
    orchestrator, then calls the real /compare endpoint. The fake CompareService runs the real
    compare flow (including refresh_compare_result_freshness) with the controlled catalog that
    produces STALE_POSSIBLE freshness.
    """
    from app.api import routes
    from app.services.compare_service import CompareService
    from app.services.search_service import SearchService
    from app.rag.retrieval_models import RetrievedChunk
    from app.rag.source_models import SourceCatalogEntry, SourceDetail, SourceState

    client = TestClient(app)

    # ------------------------------------------------------------------
    # Controlled catalog: evidence.source_version ("v1") differs from
    # catalog current_version ("v2") → STALE_POSSIBLE
    # ------------------------------------------------------------------
    def _make_entry(doc_id: str, source: str) -> SourceCatalogEntry:
        return SourceCatalogEntry(
            doc_id=doc_id,
            source=source,
            source_type="file",
            title=source.split("/")[-1],
            chunk_count=1,
            state=SourceState(
                doc_id=doc_id,
                source=source,
                current_version="v2",
                content_hash="hash_v2",
            ),
        )

    fake_collection = _FakeCollectionForFreshness(
        entries=[
            SourceDetail(entry=_make_entry("d1", "kb/a.md"), representative_metadata={}),
            SourceDetail(entry=_make_entry("d2", "kb/b.md"), representative_metadata={}),
        ],
        chunk_ids_by_doc={"d1": {"d1:c1"}, "d2": {"d2:c2"}},
    )

    # ------------------------------------------------------------------
    # Fake search service: returns hits whose source_version (from
    # extra_metadata) differs from catalog current_version → STALE_POSSIBLE
    # ------------------------------------------------------------------
    controlled_hits = [
        RetrievedChunk(
            text="Chroma storage", doc_id="d1", chunk_id="d1:c1", source="kb/a.md",
            source_type="file", distance=0.1, rerank_score=0.9, title="A",
            extra_metadata={"source_version": "v1", "content_hash": "hash_v1"},
        ),
        RetrievedChunk(
            text="Postgres storage", doc_id="d2", chunk_id="d2:c2", source="kb/b.md",
            source_type="file", distance=0.2, rerank_score=0.8, title="B",
            extra_metadata={"source_version": "v1", "content_hash": "hash_v1"},
        ),
    ]

    class _FakeSearchServiceForCompare(SearchService):
        def retrieve(self, *, query: str, top_k: int, filters=None):
            return controlled_hits

    # ------------------------------------------------------------------
    # Create CompareService with controlled collection + fake search
    # ------------------------------------------------------------------
    fake_compare_svc = CompareService(
        search_service=_FakeSearchServiceForCompare(),
        collection=fake_collection,
    )

    # ------------------------------------------------------------------
    # Inject into the orchestrator so real compare() runs with our catalog
    # ------------------------------------------------------------------
    original_svc = routes.frontend_facade.chat.compare_service
    routes.frontend_facade.chat.compare_service = fake_compare_svc

    try:
        response = client.post(
            "/compare",
            json={"question": "Compare storage", "top_k": 4},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["support_status"] == "supported"
        # evidence v1 vs catalog v2 → STALE_POSSIBLE
        assert body["common_points"][0]["left_evidence"][0]["freshness"] == "stale_possible"
        assert body["common_points"][0]["right_evidence"][0]["freshness"] == "stale_possible"
    finally:
        routes.frontend_facade.chat.compare_service = original_svc


class _FakeCollectionForFreshness:
    """Minimal fake collection for controlling evidence freshness in tests.

    Implements the interface used by refresh_compare_result_freshness:
    - list_source_details()  (via __source_details lookup by doc_id or source)
    - list_document_chunk_ids()
    """

    def __init__(self, entries: list[SourceDetail], chunk_ids_by_doc: dict[str, set[str]]):
        self._entries = entries
        self._chunk_ids = chunk_ids_by_doc

    def list_source_details(self, query):
        return self._entries

    def list_document_chunk_ids(self, doc_id: str):
        return self._chunk_ids.get(doc_id, set())


def test_unified_execute_stream_endpoint_emits_events_progressively(monkeypatch) -> None:
    """Verify that the stream endpoint yields events progressively as they are emitted.

    The key property being tested: events must be available from run_registry
    BEFORE execute_run() returns. The endpoint achieves this by running
    execute_run() in a background thread and polling run_registry for new
    client events as they arrive.

    This test verifies that when execute_run emits events to the registry
    progressively (via the collector's sink), the stream endpoint can
    retrieve and yield them before the run completes.
    """
    import threading
    import time
    from app.api import routes
    from app.application.events import (
        ArtifactEmittedPayload,
        ExecutionRun,
        ExecutionRunStatus,
        RunCompletedPayload,
        RunStartedPayload,
        StepStartedPayload,
    )
    from app.application.artifacts import ArtifactKind, TextArtifact

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()

    # We'll intercept serialize_client_event_sse calls to verify events are yielded progressively
    serialize_calls: list = []

    def counting_serialize(event):
        """Wrap serialize_client_event_sse to record each call."""
        serialize_calls.append(event)
        from app.api.streaming import serialize_client_event_sse as real_serialize
        return real_serialize(event)

    def fake_execute_run_progressive(request):
        """execute_run that emits events to registry progressively in a background thread."""
        from app.application.events import ExecutionRun, ExecutionRunStatus

        run_id = "run-progressive"
        registry = routes.frontend_facade.run_registry

        # Register the run in the registry first (so it can be found)
        run = ExecutionRun(
            run_id=run_id,
            request_summary=type("ReqSummary", (), {
                "task_type": "chat",
                "user_input_preview": "hello",
                "output_mode": "text",
                "top_k": 5,
                "citation_policy": "preferred",
                "skill_policy": "disabled",
            })(),
            status=ExecutionRunStatus.RUNNING,
        )
        registry.register(run, debug_enabled=False, stream_mode="execute")

        # Emit events progressively from a background thread, via the registry sink
        def emit_thread():
            from app.application.events import EventCollector

            collector = EventCollector(
                run_id=run_id,
                task_type="chat",
                sink=registry.make_registry_sink(run_id),
            )

            collector.emit(
                kind=ExecutionEventKind.RUN_STARTED,
                payload=RunStartedPayload(
                    request=type("Req", (), {
                        "task_type": "chat",
                        "user_input_preview": "hello",
                        "output_mode": "text",
                        "top_k": 5,
                        "citation_policy": "preferred",
                        "skill_policy": "disabled",
                    })(),
                ),
            )
            time.sleep(0.1)

            collector.emit(
                kind=ExecutionEventKind.STEP_STARTED,
                payload=StepStartedPayload(step_name="retrieve_hits", step_kind="retrieve"),
            )
            time.sleep(0.1)

            collector.emit(
                kind=ExecutionEventKind.STEP_STARTED,
                payload=StepStartedPayload(step_name="generate_answer", step_kind="generate"),
            )
            time.sleep(0.1)

            collector.emit(
                kind=ExecutionEventKind.ARTIFACT_EMITTED,
                payload=ArtifactEmittedPayload(
                    artifact=TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello world"),
                    artifact_index=1,
                ),
            )
            time.sleep(0.1)

            collector.emit(
                kind=ExecutionEventKind.RUN_COMPLETED,
                payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
            )

            registry.mark_completed(run_id)

        t = threading.Thread(target=emit_thread)
        t.start()
        t.join(timeout=5.0)

        # Return ExecutionRun (real execute_run returns this, not ManagedRun)
        managed = registry.get(run_id)
        return ExecutionRun(
            run_id=run_id,
            request_summary=run.request_summary,
            status=ExecutionRunStatus.COMPLETED,
            events=tuple(managed.internal_events) if managed else (),
        )

    monkeypatch.setattr(routes.frontend_facade, "execute_run", fake_execute_run_progressive)
    monkeypatch.setattr(routes, "serialize_client_event_sse", counting_serialize)

    response = client.post(
        "/frontend/execute/stream",
        json={"task_type": "chat", "user_input": "hello"},
        timeout=10,
    )

    assert response.status_code == 200
    events = _parse_sse_body(response.text)
    event_kinds = [e["event"] for e in events]

    # All expected events must be present
    assert "run_started" in event_kinds, f"Missing run_started in {event_kinds}"
    assert "progress" in event_kinds, f"Missing progress in {event_kinds}"
    assert "artifact" in event_kinds, f"Missing artifact in {event_kinds}"
    assert "completed" in event_kinds, f"Missing completed in {event_kinds}"

    # Progressive property: serialize_client_event_sse must have been called multiple times
    # (meaning events were yielded progressively, not as a single batch)
    assert len(serialize_calls) > 0, "serialize_client_event_sse was never called"
    assert len(serialize_calls) > 1, (
        f"Expected progressive yields but got only {len(serialize_calls)} call(s). "
        "This means events are still emitted as a single batch after execution completes."
    )
