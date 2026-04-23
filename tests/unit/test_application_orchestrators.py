"""Unit tests for application-layer orchestrators and facade assembly."""

from dataclasses import dataclass

from app.application.artifacts import ArtifactKind, MermaidArtifact, SearchResultsArtifact, SkillResultArtifact, StructuredJsonArtifact, TextArtifact
from app.application.events import ExecutionEventKind, ExecutionRunStatus
from app.application.models import OutputMode, RetrievalOptions, SkillPolicy, SkillPolicyMode, TaskType, UnifiedExecutionRequest
from app.application.orchestrators import ChatOrchestrator, FrontendFacade, KnowledgeBaseOrchestrator, SkillOrchestrator
from app.application.run_control import RunRegistry, RunControlConfig
from app.rag.retrieval_models import CitationRecord, ComparedPoint, EvidenceObject, GroundedAnswer, GroundedCompareResult, RetrievedChunk, RetrievalFilters, SearchHitRecord, SearchResult
from app.runtime.factory import RuntimeFactory
from app.runtime.models import (
    ExecutionPolicy,
    RuntimeCapabilities,
    RuntimeProfile,
    RuntimeSelectionMode,
)
from app.runtime.profiles import RuntimeProfileRegistry
from app.runtime.registry import RuntimeRegistry
from app.runtime.resolver import RuntimeResolver
from app.services.service_models import ChatServiceResult, CompareServiceResult, IngestServiceResult, SearchServiceResult, SummarizeServiceResult, UseCaseMetadata
from app.services.search_service import SearchService
from app.services.chat_service import ChatService


@dataclass
class FakeQueryServices:
    search_result: object
    chat_result: object
    summarize_result: object
    compare_result: object | None = None

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        return self.search_result

    def chat(self, **kwargs):
        self.chat_kwargs = kwargs
        return self.chat_result

    def summarize(self, **kwargs):
        self.summarize_kwargs = kwargs
        return self.summarize_result

    def compare(self, **kwargs):
        self.compare_kwargs = kwargs
        return self.compare_result


@dataclass
class FakeKnowledgeBaseServices:
    ingest_result: object
    list_result: object

    def ingest(self, **kwargs):
        self.ingest_kwargs = kwargs
        return self.ingest_result

    def list_sources(self, **kwargs):
        self.list_kwargs = kwargs
        return self.list_result


def test_chat_orchestrator_delegates_to_services() -> None:
    search_result = SearchServiceResult(search_result=type("SearchResult", (), {"query": "q", "top_k": 1, "hits": [], "to_api_dict": lambda self: {}})())
    chat_result = ChatServiceResult(answer="a", citations=[])
    summarize_result = SummarizeServiceResult(summary="s", citations=[])
    compare_result = CompareServiceResult(compare_result=GroundedCompareResult(query="q"), citations=[])
    orchestrator = ChatOrchestrator(
        search_service=FakeQueryServices(search_result, chat_result, summarize_result, compare_result),
        chat_service=FakeQueryServices(search_result, chat_result, summarize_result, compare_result),
        summarize_service=FakeQueryServices(search_result, chat_result, summarize_result, compare_result),
        compare_service=FakeQueryServices(search_result, chat_result, summarize_result, compare_result),
    )

    assert orchestrator.search(query="q", top_k=1) is search_result
    assert orchestrator.chat(query="q", top_k=1) is chat_result
    assert orchestrator.summarize(topic="q", top_k=1) is summarize_result
    assert orchestrator.compare(question="q", top_k=1) is compare_result


def test_knowledge_base_orchestrator_delegates_to_services() -> None:
    ingest_result = IngestServiceResult(batch=type("Batch", (), {"documents": 0, "chunks": 0, "ingested_sources": [], "failed_sources": [], "to_api_dict": lambda self: {}})())
    list_result = object()
    orchestrator = KnowledgeBaseOrchestrator(
        ingest_service=FakeKnowledgeBaseServices(ingest_result, list_result),
        catalog_service=FakeKnowledgeBaseServices(ingest_result, list_result),
    )

    assert orchestrator.ingest(rebuild=True, urls=["https://example.com"]) is ingest_result
    assert orchestrator.list_sources(source_type="url") is list_result


def test_skill_orchestrator_executes_registry_skill() -> None:
    result = SkillOrchestrator().execute_skill(name="echo", arguments={"text": "hello"}, debug=True)

    assert result.ok is True
    assert result.output["text"] == "hello"
    assert result.output["debug"] is True


def test_frontend_facade_exposes_orchestrators() -> None:
    facade = FrontendFacade()
    assert isinstance(facade.chat, ChatOrchestrator)
    assert isinstance(facade.knowledge_base, KnowledgeBaseOrchestrator)
    assert isinstance(facade.skills, SkillOrchestrator)


class FakeRuntime:
    runtime_name = "langchain"
    provider_name = "fake-provider"
    capabilities = RuntimeCapabilities(supports_chat=True, supports_summarize=True)

    def generate(self, request):
        from app.runtime.models import RuntimeResponse
        return RuntimeResponse(
            text="fake generated text",
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


def _runtime_stack():
    profile_registry = RuntimeProfileRegistry()
    profile_registry.register(
        RuntimeProfile(
            profile_id="default_cloud",
            display_name="Default Cloud",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="gpt-4o-mini",
            tags=("cloud", "quality"),
        )
    )
    runtime_registry = RuntimeRegistry(default_adapter_kind="langchain")
    runtime_registry.register(
        "langchain",
        lambda profile: FakeRuntime(),
        default_capabilities=RuntimeCapabilities(supports_chat=True, supports_summarize=True),
        make_default=True,
    )
    resolver = RuntimeResolver(runtime_registry=runtime_registry, profile_registry=profile_registry)
    factory = RuntimeFactory(runtime_registry=runtime_registry, profile_registry=profile_registry)
    return profile_registry, resolver, factory


def _run_registry() -> RunRegistry:
    return RunRegistry(config=RunControlConfig(max_runs=20, recent_event_buffer_size=20, completed_run_ttl_seconds=60, heartbeat_interval_seconds=2))


def test_unified_execution_chat_returns_runtime_profile_metadata(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(
            answer="chat response",
            citations=[],
            grounded_answer=GroundedAnswer(
                answer="chat response",
                evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="proof", score=0.2),),
            ),
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded", support_status="supported"),
        )

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_metadata=True,
        )
    )

    assert response.primary_text() == "chat response"
    assert isinstance(response.artifacts[0], TextArtifact)
    assert response.grounded_answer is not None
    assert response.grounded_answer.support_status.value == "supported"
    assert response.artifacts[0].metadata["grounded_answer"]["support_status"] == "supported"
    assert response.metadata.selected_profile_id == "default_cloud"
    assert response.metadata.selection_reason is not None
    assert response.metadata.artifact_kinds_returned == ("text",)
    assert response.execution_summary.primary_artifact_kind == "text"


def test_unified_execution_chat_collects_stable_event_sequence(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(
            answer="chat response",
            citations=[],
            grounded_answer=GroundedAnswer(answer="chat response"),
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded", support_status="supported"),
        )

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_events=True,
            include_metadata=True,
        )
    )

    kinds = [event.kind.value for event in run.events]
    assert run.status == ExecutionRunStatus.COMPLETED
    assert kinds[0] == "run_started"
    assert kinds[1] == "plan_built"
    assert "metadata_updated" in kinds
    assert kinds[-1] == "run_completed"
    assert any(event.kind == ExecutionEventKind.ARTIFACT_EMITTED for event in run.events)
    assert tuple(event.sequence for event in run.events) == tuple(range(1, len(run.events) + 1))


def test_unified_execution_chat_preserves_grounded_answer_in_compatibility_entrypoint(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(
            answer="chat response",
            citations=[CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="proof")],
            grounded_answer=GroundedAnswer(
                answer="chat response",
                evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="proof", score=0.2),),
            ),
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded", support_status="supported"),
        )

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    result = facade.execute_chat_request(query="hello", top_k=3)

    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "supported"
    assert result.grounded_answer.evidence[0].chunk_id == "c1"


def test_unified_execution_summarize_supports_mermaid_with_execution_policy(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_summarize_with_runtime(*, request, runtime, precomputed_hits=None):
        return SummarizeServiceResult(
            summary="summary response",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic", output_format="mermaid"),
            structured_output="mindmap\n  root((summary))",
        )

    monkeypatch.setattr(chat_orchestrator, "run_summarize_with_runtime", fake_run_summarize_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.SUMMARIZE,
            user_input="storage",
            output_mode=OutputMode.MERMAID,
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_metadata=True,
        )
    )

    assert response.primary_text() == "summary response"
    assert isinstance(response.primary_block(OutputMode.MERMAID), MermaidArtifact)
    assert response.execution_summary.selected_profile_id == "default_cloud"


def test_unified_execution_summarize_emits_mermaid_artifact_event(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_summarize_with_runtime(*, request, runtime, precomputed_hits=None):
        return SummarizeServiceResult(
            summary="summary response",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic", output_format="mermaid"),
            structured_output="mindmap\n  root((summary))",
        )

    monkeypatch.setattr(chat_orchestrator, "run_summarize_with_runtime", fake_run_summarize_with_runtime)

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.SUMMARIZE,
            user_input="storage",
            output_mode=OutputMode.MERMAID,
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_events=True,
        )
    )

    artifact_events = [event for event in run.events if event.kind == ExecutionEventKind.ARTIFACT_EMITTED]
    assert any(isinstance(event.payload.artifact, MermaidArtifact) for event in artifact_events)


def test_chat_summary_request_routes_to_summarize(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    class FakePipeline:
        def run(self, **kwargs):
            return {"hits": []}

    def fail_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        raise AssertionError("summary intent should not run chat")

    def fake_run_summarize_with_runtime(*, request, runtime, precomputed_hits=None):
        assert request.task_type == TaskType.SUMMARIZE
        assert request.task_options["mode"] == "basic"
        return SummarizeServiceResult(
            summary="summary response",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic"),
        )

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fail_run_chat_with_runtime)
    monkeypatch.setattr(chat_orchestrator, "run_summarize_with_runtime", fake_run_summarize_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="请总结一下知识库中的主要内容",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_metadata=True,
        )
    )

    assert response.task_type == TaskType.SUMMARIZE
    assert response.primary_text() == "summary response"
    assert response.metadata.mode == "basic"


def test_fact_question_stays_on_chat_route() -> None:
    facade = FrontendFacade()
    request = UnifiedExecutionRequest(
        task_type=TaskType.CHAT,
        user_input="什么是RAG，它解决了什么问题",
    )

    routed = facade._route_chat_summary_request(request)

    assert routed.task_type == TaskType.CHAT


def test_summarize_uses_expanded_retrieval_pool(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )
    observed_top_k: list[int] = []

    class FakePipeline:
        def run(self, **kwargs):
            observed_top_k.append(kwargs["top_k"])
            return {"hits": []}

    def fake_run_summarize_with_runtime(*, request, runtime, precomputed_hits=None):
        return SummarizeServiceResult(
            summary="summary response",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic"),
        )

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(chat_orchestrator, "run_summarize_with_runtime", fake_run_summarize_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.SUMMARIZE,
            user_input="summarize the knowledge base",
            retrieval=RetrievalOptions(top_k=5),
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
        )
    )

    assert response.task_type == TaskType.SUMMARIZE
    assert observed_top_k == [15]


def test_chat_keeps_requested_retrieval_pool(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )
    observed_top_k: list[int] = []

    class FakePipeline:
        def run(self, **kwargs):
            observed_top_k.append(kwargs["top_k"])
            return {"hits": []}

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(
            answer="chat response",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded"),
        )

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="what is RAG",
            retrieval=RetrievalOptions(top_k=5),
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
        )
    )

    assert response.task_type == TaskType.CHAT
    assert observed_top_k == [5]


def test_single_source_general_chat_returns_scope_guardrail(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    class FailingPipeline:
        def run(self, **kwargs):
            raise AssertionError("scope guardrail should skip retrieval")

    def fail_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        raise AssertionError("scope guardrail should skip generation")

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FailingPipeline())
    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fail_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="\u4ecb\u7ecdrag",
            retrieval=RetrievalOptions(filters=RetrievalFilters(sources=("kb/doc.md",))),
            include_metadata=True,
        )
    )

    assert response.task_type == TaskType.CHAT
    assert response.citations == ()
    assert "单个文档" in response.primary_text()
    assert response.metadata.mode == "scope_guardrail"
    assert response.metadata.insufficient_evidence is True
    assert response.metadata.refusal_reason == "out_of_scope"
    assert response.metadata.issues[0].code == "scope_guardrail"
    assert response.artifacts[0].metadata["scope_guardrail"] is True


def test_single_source_global_summary_returns_scope_guardrail_after_routing(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    class FailingPipeline:
        def run(self, **kwargs):
            raise AssertionError("scope guardrail should skip retrieval")

    def fail_run_summarize_with_runtime(*, request, runtime, precomputed_hits=None):
        raise AssertionError("scope guardrail should skip summarization")

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FailingPipeline())
    monkeypatch.setattr(chat_orchestrator, "run_summarize_with_runtime", fail_run_summarize_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="\u8bf7\u603b\u7ed3\u4e00\u4e0b\u77e5\u8bc6\u5e93\u4e2d\u7684\u4e3b\u8981\u5185\u5bb9",
            retrieval=RetrievalOptions(filters=RetrievalFilters(sources=("kb/doc.md",))),
            include_metadata=True,
        )
    )

    assert response.task_type == TaskType.SUMMARIZE
    assert "取消单文档范围" in response.primary_text()
    assert response.metadata.mode == "scope_guardrail"
    assert response.citations == ()


def test_single_source_document_specific_question_bypasses_scope_guardrail(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )
    observed_filters: list[RetrievalFilters | None] = []

    class FakePipeline:
        def run(self, **kwargs):
            observed_filters.append(kwargs["filters"])
            return {"hits": []}

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(
            answer="document-specific answer",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=0, mode="grounded"),
        )

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="\u8fd9\u7bc7\u6587\u6863\u8bb2\u4e86\u4ec0\u4e48",
            retrieval=RetrievalOptions(filters=RetrievalFilters(sources=("kb/doc.md",))),
            include_metadata=True,
        )
    )

    assert response.primary_text() == "document-specific answer"
    assert observed_filters == [RetrievalFilters(sources=("kb/doc.md",))]
    assert response.metadata.mode != "scope_guardrail"


def test_global_general_chat_bypasses_scope_guardrail(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )
    observed_filters: list[RetrievalFilters | None] = []

    class FakePipeline:
        def run(self, **kwargs):
            observed_filters.append(kwargs["filters"])
            return {"hits": []}

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(
            answer="global answer",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=0, mode="grounded"),
        )

    monkeypatch.setattr(chat_orchestrator, "_retrieval_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="\u4ecb\u7ecdrag",
            include_metadata=True,
        )
    )

    assert response.primary_text() == "global answer"
    assert observed_filters == [None]
    assert response.metadata.mode != "scope_guardrail"


def test_unified_execution_search_returns_search_results_artifact(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    search_result = SearchServiceResult(
        search_result=SearchResult(
            query="search me",
            top_k=2,
            hits=[
                SearchHitRecord(
                    chunk=RetrievedChunk(
                        text="result snippet",
                        doc_id="d1",
                        chunk_id="c1",
                        source="kb/doc.md",
                        source_type="file",
                        title="doc",
                        distance=0.2,
                    ),
                    citation=CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="result snippet"),
                )
            ],
        ),
        metadata=UseCaseMetadata(retrieved_count=1),
    )
    monkeypatch.setattr(chat_orchestrator, "search", lambda **kwargs: search_result)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.SEARCH,
            user_input="search me",
            include_metadata=True,
        )
    )

    assert isinstance(response.artifacts[0], SearchResultsArtifact)
    assert response.artifacts[0].items[0].chunk_id == "c1"
    assert response.metadata.artifact_kinds_returned == ("search_results",)
    assert response.metadata.search_result_count == 1


def test_unified_execution_search_has_stable_step_events(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
    )

    search_result = SearchServiceResult(
        search_result=SearchResult(
            query="search me",
            top_k=1,
            hits=[],
        ),
        metadata=UseCaseMetadata(retrieved_count=0, partial_failure=True, warnings=("empty result",)),
    )
    monkeypatch.setattr(chat_orchestrator, "search", lambda **kwargs: search_result)

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.SEARCH,
            user_input="search me",
            include_events=True,
            include_metadata=True,
        )
    )

    step_kinds = [event.kind.value for event in run.events if event.kind in {ExecutionEventKind.STEP_STARTED, ExecutionEventKind.STEP_COMPLETED}]
    assert step_kinds[:2] == ["step_started", "step_started"]
    assert "warning_emitted" in [event.kind.value for event in run.events]
    assert run.final_response is not None
    assert run.final_response.metadata.partial_failure is True


def test_unified_execution_compare_matches_direct_compare_semantics(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    compare_result = CompareServiceResult(
        compare_result=GroundedCompareResult(
            query="compare storage",
            common_points=(
                ComparedPoint(
                    statement="Both docs discuss storage.",
                    left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="A storage", score=0.2),),
                    right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="B storage", score=0.3),),
                ),
            ),
            differences=(
                ComparedPoint(
                    statement="The docs use different storage backends.",
                    left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="A storage", score=0.2),),
                    right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="B storage", score=0.3),),
                ),
            ),
        ),
        citations=[
            CitationRecord(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="A storage"),
            CitationRecord(doc_id="d2", chunk_id="c2", source="kb/b.md", snippet="B storage"),
        ],
        metadata=UseCaseMetadata(retrieved_count=2, mode="grounded_compare", support_status="supported"),
    )

    monkeypatch.setattr(chat_orchestrator, "compare", lambda **kwargs: compare_result)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.COMPARE,
            user_input="compare storage",
            output_mode=OutputMode.STRUCTURED,
            include_metadata=True,
        )
    )
    direct = facade.execute_compare_request(question="compare storage", top_k=5)

    assert response.compare_result is not None
    assert response.compare_result.support_status.value == "supported"
    # Note: freshness is FRESH for mock evidence without source_version (refresh_compare_result_freshness
    # short-circuits when evidence.source_version is None, returning FRESH directly).
    assert response.compare_result.differences[0].left_evidence[0].freshness.value == "fresh"
    assert response.artifacts[0].metadata["compare_result"]["support_status"] == "supported"
    assert direct.compare_result.query == response.compare_result.query
    assert direct.compare_result.differences[0].statement == response.compare_result.differences[0].statement


def test_unified_execution_structured_mode_returns_structured_json_artifact(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
    )

    def fake_run_summarize_with_runtime(*, request, runtime, precomputed_hits=None):
        return SummarizeServiceResult(
            summary="summary response",
            citations=[],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic", output_format="text"),
        )

    monkeypatch.setattr(chat_orchestrator, "run_summarize_with_runtime", fake_run_summarize_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.SUMMARIZE,
            user_input="storage",
            output_mode=OutputMode.STRUCTURED,
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_metadata=True,
        )
    )

    assert isinstance(response.artifacts[0], TextArtifact)
    assert isinstance(response.artifacts[1], StructuredJsonArtifact)
    assert response.artifacts[1].data["summary"] == "summary response"


def test_skill_disabled_does_not_invoke_skill(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    skill_orchestrator = SkillOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        skills=skill_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(answer="chat response", citations=[], metadata=UseCaseMetadata(retrieved_count=1))

    def fail_execute_skill(**kwargs):
        raise AssertionError("skill should not be invoked")

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)
    monkeypatch.setattr(skill_orchestrator, "execute_skill", fail_execute_skill)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            skill_policy=SkillPolicy(mode=SkillPolicyMode.DISABLED),
            include_metadata=True,
        )
    )

    assert response.execution_summary.skill_invocations == ()
    assert not any(isinstance(artifact, SkillResultArtifact) for artifact in response.artifacts)


def test_allowlisted_echo_skill_executes_via_plan_step(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        skills=SkillOrchestrator(),
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(answer="chat response", citations=[], metadata=UseCaseMetadata(retrieved_count=1))

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="echo me",
            skill_policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowlist=("echo",)),
            include_metadata=True,
        )
    )

    assert response.execution_summary.skill_invocations[0].name == "echo"
    assert response.metadata.skill_invocations[0].output_preview == "echo me"
    assert any(isinstance(artifact, SkillResultArtifact) for artifact in response.artifacts)
    assert response.metadata.skill_artifact_count == 1


def test_unified_execution_failure_collects_run_failed_event(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fail_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        raise RuntimeError("chat exploded")

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fail_run_chat_with_runtime)

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            include_events=True,
        )
    )

    assert run.status == ExecutionRunStatus.FAILED
    assert run.error is not None
    assert run.events[-1].kind == ExecutionEventKind.RUN_FAILED
    assert run.events[-1].payload.detail == "chat exploded"


def test_unified_execution_honors_cancellation_request_at_safe_boundary(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    registry = _run_registry()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=registry,
    )

    original_register = registry.register

    def register_and_cancel(run, **kwargs):
        managed = original_register(run, **kwargs)
        registry.request_cancellation(run.run_id)
        return managed

    monkeypatch.setattr(registry, "register", register_and_cancel)

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            include_events=True,
        )
    )

    assert run.status == ExecutionRunStatus.CANCELLED
    assert run.events[-1].kind == ExecutionEventKind.RUN_FAILED
    assert "cancelled" in run.events[-1].payload.detail.lower()


# -----------------------------------------------------------------------
# Tests for unified retrieval pipeline
# -----------------------------------------------------------------------

def test_precomputed_hits_equivalence_chat(monkeypatch) -> None:
    """precomputed_hits=<hits> and precomputed_hits=None must yield the same answer.

    This verifies that passing hits from the shared pipeline into ChatService.chat()
    produces the same result as letting ChatService retrieve its own hits, provided
    the hits are identical. The service must skip retrieval entirely when precomputed
    hits are supplied.
    """
    controlled_hits = [
        RetrievedChunk(
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
        ),
    ]

    retrieval_call_count = 0

    class TrackedSearchService(SearchService):
        def retrieve(self, query, top_k, filters=None):
            nonlocal retrieval_call_count
            retrieval_call_count += 1
            return controlled_hits

    search_service = TrackedSearchService()

    # Path A: service retrieves its own hits
    retrieval_call_count = 0
    chat_service_a = ChatService(search_service=search_service, runtime=FakeRuntime())
    result_a = chat_service_a.chat(query="what does MindDock store?", top_k=5)

    # Path B: precomputed_hits supplied (as the shared pipeline would do)
    retrieval_call_count = 0
    chat_service_b = ChatService(search_service=search_service, runtime=FakeRuntime())
    result_b = chat_service_b.chat(
        query="what does MindDock store?",
        top_k=5,
        precomputed_hits=controlled_hits,
    )

    assert retrieval_call_count == 0, "precomputed_hits must skip retrieval"
    # Same answer
    assert result_a.answer == result_b.answer
    # Same grounded evidence count
    assert len(result_a.grounded_answer.evidence) == len(result_b.grounded_answer.evidence)
    # Same support status
    assert result_a.grounded_answer.support_status == result_b.grounded_answer.support_status


def test_precomputed_hits_equivalence_summarize(monkeypatch) -> None:
    """Same equivalence check as above but for the SummarizeService path."""
    controlled_hits = [
        RetrievedChunk(
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
        ),
    ]

    retrieval_call_count = 0

    class TrackedSearchService(SearchService):
        def retrieve(self, query, top_k, filters=None):
            nonlocal retrieval_call_count
            retrieval_call_count += 1
            return controlled_hits

    search_service = TrackedSearchService()

    from app.services.summarize_service import SummarizeService

    # Path A: service retrieves its own hits
    retrieval_call_count = 0
    summarize_service_a = SummarizeService(
        search_service=search_service,
        runtime=FakeRuntime(),
    )
    result_a = summarize_service_a.summarize(topic="MindDock storage", top_k=5)

    # Path B: precomputed_hits supplied
    retrieval_call_count = 0
    summarize_service_b = SummarizeService(
        search_service=search_service,
        runtime=FakeRuntime(),
    )
    result_b = summarize_service_b.summarize(
        topic="MindDock storage",
        top_k=5,
        precomputed_hits=controlled_hits,
    )

    assert retrieval_call_count == 0, "precomputed_hits must skip retrieval"
    assert result_a.summary == result_b.summary


def test_unified_pipeline_retrieval_called_once_in_chat(monkeypatch) -> None:
    """The facade must run the unified pipeline once for CHAT and pass the hits
    to the service; SearchService.retrieve must be called exactly once."""
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    registry = _run_registry()

    retrieval_count = 0
    original_retrieve = SearchService.retrieve

    def counting_retrieve(self, query, top_k, filters=None):
        nonlocal retrieval_count
        retrieval_count += 1
        return original_retrieve(self, query, top_k, filters)

    monkeypatch.setattr(SearchService, "retrieve", counting_retrieve)

    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=registry,
    )

    retrieval_count = 0
    facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
        )
    )

    assert retrieval_count == 1, f"Expected exactly 1 retrieval call, got {retrieval_count}"


def test_unified_pipeline_retrieval_called_once_in_summarize(monkeypatch) -> None:
    """Same check as above but for the SUMMARIZE task type."""
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    registry = _run_registry()

    retrieval_count = 0
    original_retrieve = SearchService.retrieve

    def counting_retrieve(self, query, top_k, filters=None):
        nonlocal retrieval_count
        retrieval_count += 1
        return original_retrieve(self, query, top_k, filters)

    monkeypatch.setattr(SearchService, "retrieve", counting_retrieve)

    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=registry,
    )

    retrieval_count = 0
    facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.SUMMARIZE,
            user_input="hello",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
        )
    )

    assert retrieval_count == 1, f"Expected exactly 1 retrieval call, got {retrieval_count}"


def test_unified_pipeline_emits_retrieval_trace_events(monkeypatch) -> None:
    """Pipeline events (retrieval_started/completed, rerank_completed,
    compress_completed, retrieval_pipeline_completed) must be emitted for
    CHAT and SUMMARIZE tasks."""
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    registry = _run_registry()
    controlled_hits = [
        RetrievedChunk(
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
        ),
    ]

    def fake_retrieve(self, query, top_k, filters=None):
        return controlled_hits

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        assert precomputed_hits == controlled_hits
        return ChatServiceResult(
            answer="chat response",
            citations=[],
            grounded_answer=GroundedAnswer(answer="chat response"),
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded", support_status="supported"),
        )

    monkeypatch.setattr(SearchService, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    facade = FrontendFacade(
        chat=chat_orchestrator,
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=registry,
    )

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="hello",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            include_events=True,
        )
    )

    event_kinds = {e.kind for e in run.events}
    expected_pipeline_events = {
        ExecutionEventKind.RETRIEVAL_STARTED,
        ExecutionEventKind.RETRIEVAL_COMPLETED,
        ExecutionEventKind.RERANK_COMPLETED,
        ExecutionEventKind.COMPRESS_COMPLETED,
        ExecutionEventKind.RETRIEVAL_PIPELINE_COMPLETED,
    }
    assert expected_pipeline_events.issubset(event_kinds), (
        f"Missing pipeline events. Expected {expected_pipeline_events}, got {event_kinds & expected_pipeline_events}"
    )

    # verify retrieval_pipeline_completed payload has non-zero hit counts
    pipeline_done = next(
        e for e in run.events if e.kind == ExecutionEventKind.RETRIEVAL_PIPELINE_COMPLETED
    )
    assert pipeline_done.payload is not None
    from app.application.events import RetrievalPipelineCompletedPayload
    assert isinstance(pipeline_done.payload, RetrievalPipelineCompletedPayload)
    assert pipeline_done.payload.retrieved_hits == len(controlled_hits)
