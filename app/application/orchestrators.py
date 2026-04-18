"""Frontend-facing orchestration layer built on top of application services."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.application.artifacts import ArtifactBuilder, ArtifactKind, ArtifactMapper
from app.application.client_events import EventProjector, get_event_projector
from app.application.events import (
    ArtifactEmittedPayload,
    EventCollector,
    ExecutionMetadataDelta,
    ExecutionEventKind,
    ExecutionRequestSummary,
    ExecutionRun,
    ExecutionRunStatus,
    MetadataUpdatedPayload,
    PlanBuiltPayload,
    RetrievalPipelineCompletedPayload,
    RetrievalPipelineProgressPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    StepCompletedPayload,
    StepStartedPayload,
    WarningEmittedPayload,
    build_run_id,
)
from app.application.models import (
    CitationPolicy,
    ExecutionDecision,
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionStep,
    ExecutionSummary,
    OutputMode,
    RetrievalOptions,
    SkillInvocationRecord,
    SkillPolicy,
    SkillPolicyMode,
    StepKind,
    TaskType,
    UnifiedExecutionRequest,
    UnifiedExecutionResponse,
)
from app.application.run_control import RunRegistry, get_run_registry
from app.core.exceptions import SkillExecutionFailedError, SkillNotAllowedError, UnsupportedExecutionModeError
from app.runtime import GenerationRuntime, RuntimeSelectionMode, RuntimeSelectionPolicy, RuntimeSelectionRequest
from app.runtime.factory import RuntimeFactory, get_runtime_factory
from app.runtime.profiles import RuntimeProfileRegistry, get_runtime_profile_registry
from app.runtime.resolver import RuntimeResolver, get_runtime_resolver
from app.services.catalog_service import CatalogService
from app.services.chat_service import ChatService
from app.services.compare_service import CompareService
from app.services.ingest_service import IngestService
from app.services.participation import extract_participating_doc_ids, load_projected_sources
from app.services.search_service import SearchService
from app.services.service_models import (
    ChatServiceResult,
    CompareServiceResult,
    SkillInvocation,
    SummarizeServiceResult,
)
from app.services.summarize_service import SummarizeService
from app.skills import (
    SkillCatalogDetail,
    SkillCatalogEntry,
    SkillExecutionContext,
    SkillInvocationRequest,
    SkillInvocationResult,
    SkillInvocationSource,
    SkillRegistry,
    get_skill_registry,
)
from app.skills.policy import SkillAccessDecision, SkillAccessEvaluator
from app.workflows.unified_pipeline import RetrievalPipeline


@dataclass
class ChatOrchestrator:
    """High-level query orchestration for search/chat/summarize consumers."""

    search_service: SearchService | None = None
    chat_service: ChatService | None = None
    summarize_service: SummarizeService | None = None
    compare_service: CompareService | None = None

    def search(self, *, query: str, top_k: int, filters=None):
        return self._search_service().search(query=query, top_k=top_k, filters=filters)

    def chat(self, *, query: str, top_k: int, filters=None):
        return self._chat_service().chat(query=query, top_k=top_k, filters=filters)

    def summarize(self, *, topic: str, top_k: int, filters=None, mode: str = "basic", output_format: str = "text"):
        return self._summarize_service().summarize(
            topic=topic,
            top_k=top_k,
            filters=filters,
            mode=mode,
            output_format=output_format,
        )

    def compare(self, *, question: str, top_k: int, filters=None, precomputed_hits=None):
        return self._compare_service().compare(
            question=question,
            top_k=top_k,
            filters=filters,
            precomputed_hits=precomputed_hits,
        )

    def build_execution_plan(self, request: UnifiedExecutionRequest) -> ExecutionPlan:
        return self.build_execution_plan_with_skills(request)

    def build_execution_plan_with_skills(
        self,
        request: UnifiedExecutionRequest,
        *,
        planned_skill_ids: tuple[str, ...] = (),
    ) -> ExecutionPlan:
        """Compile a lightweight execution plan for knowledge-style tasks."""

        skill_steps = tuple(
            ExecutionStep(kind=StepKind.SKILL_INVOKE, name=skill_name, metadata={"skill_name": skill_name})
            for skill_name in planned_skill_ids
        )

        if request.task_type == TaskType.CHAT:
            if request.output_mode != OutputMode.TEXT:
                raise UnsupportedExecutionModeError(detail=f"Chat does not support output mode '{request.output_mode.value}'.")
            return ExecutionPlan(
                task_type=request.task_type,
                steps=(
                    ExecutionStep(kind=StepKind.RETRIEVE, name="retrieve_evidence"),
                    ExecutionStep(kind=StepKind.RERANK, name="rerank_hits"),
                    ExecutionStep(kind=StepKind.COMPRESS, name="compress_context"),
                    ExecutionStep(kind=StepKind.GENERATE, name="generate_answer"),
                    *skill_steps,
                    ExecutionStep(kind=StepKind.FORMAT_OUTPUT, name="format_text_output", metadata={"output_mode": "text"}),
                ),
                decision=ExecutionDecision(requires_runtime=True, supports_citations=request.citation_policy != CitationPolicy.NONE),
            )

        if request.task_type == TaskType.SUMMARIZE:
            summarize_mode = str(request.task_options.get("mode") or "basic")
            steps = [
                ExecutionStep(kind=StepKind.RETRIEVE, name="retrieve_evidence"),
                ExecutionStep(kind=StepKind.RERANK, name="rerank_hits"),
                ExecutionStep(kind=StepKind.COMPRESS, name="compress_context"),
            ]
            if summarize_mode == "map_reduce":
                steps.extend(
                    (
                        ExecutionStep(kind=StepKind.SUMMARIZE_MAP, name="map_document_summaries"),
                        ExecutionStep(kind=StepKind.SUMMARIZE_REDUCE, name="reduce_summary"),
                    )
                )
            else:
                steps.append(ExecutionStep(kind=StepKind.GENERATE, name="generate_summary"))
            steps.extend(skill_steps)
            steps.append(
                ExecutionStep(
                    kind=StepKind.FORMAT_OUTPUT,
                    name="format_output",
                    metadata={"output_mode": request.output_mode.value},
                )
            )
            return ExecutionPlan(
                task_type=request.task_type,
                steps=tuple(steps),
                decision=ExecutionDecision(
                    requires_runtime=True,
                    requires_structured_output=False,
                    supports_citations=request.citation_policy != CitationPolicy.NONE,
                ),
            )

        if request.task_type == TaskType.SEARCH:
            return ExecutionPlan(
                task_type=request.task_type,
                steps=(
                    ExecutionStep(kind=StepKind.RETRIEVE, name="retrieve_hits"),
                    ExecutionStep(kind=StepKind.RERANK, name="rerank_hits"),
                    ExecutionStep(kind=StepKind.COMPRESS, name="select_hits"),
                    ExecutionStep(kind=StepKind.FORMAT_OUTPUT, name="format_search_output", metadata={"output_mode": "text"}),
                ),
                decision=ExecutionDecision(requires_runtime=False, supports_citations=True),
            )

        if request.task_type == TaskType.COMPARE:
            return ExecutionPlan(
                task_type=request.task_type,
                steps=(
                    ExecutionStep(kind=StepKind.RETRIEVE, name="retrieve_evidence"),
                    ExecutionStep(kind=StepKind.RERANK, name="rerank_hits"),
                    ExecutionStep(kind=StepKind.COMPRESS, name="compress_context"),
                    ExecutionStep(kind=StepKind.FORMAT_OUTPUT, name="format_compare_output", metadata={"output_mode": "structured"}),
                ),
                decision=ExecutionDecision(requires_runtime=False, requires_structured_output=True, supports_citations=True),
            )

        raise UnsupportedExecutionModeError(detail=f"Task type '{request.task_type.value}' is not supported yet.")

    def run_chat_with_runtime(
        self,
        *,
        request: UnifiedExecutionRequest,
        runtime: GenerationRuntime,
        precomputed_hits: list | None = None,
    ) -> ChatServiceResult:
        """Execute chat with an explicitly selected runtime.

        Args:
            precomputed_hits: If provided, the chat service skips retrieval and uses
                these hits directly, avoiding duplicate retrieval work.
        """
        service = replace(self._chat_service(), runtime=runtime)
        return service.chat(
            query=request.user_input,
            top_k=request.retrieval.top_k,
            filters=request.retrieval.filters,
            precomputed_hits=precomputed_hits,
        )

    def run_summarize_with_runtime(
        self,
        *,
        request: UnifiedExecutionRequest,
        runtime: GenerationRuntime,
        precomputed_hits: list | None = None,
    ) -> SummarizeServiceResult:
        """Execute summarize with an explicitly selected runtime.

        Args:
            precomputed_hits: If provided, the summarize service skips the LangGraph
                retrieval workflow and uses these hits directly.
        """
        service = replace(self._summarize_service(), runtime=runtime)
        mode = str(request.task_options.get("mode") or "basic")
        output_format = "mermaid" if request.output_mode == OutputMode.MERMAID else "text"
        return service.summarize(
            topic=request.user_input,
            top_k=request.retrieval.top_k,
            filters=request.retrieval.filters,
            mode=mode,
            output_format=output_format,
            precomputed_hits=precomputed_hits,
        )

    def _search_service(self) -> SearchService:
        if self.search_service is None:
            self.search_service = SearchService()
        return self.search_service

    def _chat_service(self) -> ChatService:
        if self.chat_service is None:
            self.chat_service = ChatService(search_service=self._search_service())
        return self.chat_service

    def _summarize_service(self) -> SummarizeService:
        if self.summarize_service is None:
            self.summarize_service = SummarizeService(search_service=self._search_service())
        return self.summarize_service

    def _compare_service(self) -> CompareService:
        if self.compare_service is None:
            self.compare_service = CompareService(search_service=self._search_service())
        return self.compare_service

    def _retrieval_pipeline(self) -> RetrievalPipeline:
        """Shared retrieve → rerank → compress pipeline backed by LangGraph."""
        return RetrievalPipeline(search_service=self._search_service())


@dataclass
class KnowledgeBaseOrchestrator:
    """High-level orchestration for ingest and source-management flows."""

    ingest_service: IngestService | None = None
    catalog_service: CatalogService | None = None

    def ingest(self, *, rebuild: bool = False, urls: list[str] | None = None):
        return self._ingest_service().ingest(rebuild=rebuild, urls=urls)

    def list_sources(self, *, source_type: str | None = None):
        return self._catalog_service().list_sources(source_type=source_type)

    def get_source_detail(self, *, doc_id: str | None = None, source: str | None = None, include_admin_metadata: bool = False):
        return self._catalog_service().get_source_detail(
            doc_id=doc_id,
            source=source,
            include_admin_metadata=include_admin_metadata,
        )

    def inspect_source(
        self,
        *,
        doc_id: str | None = None,
        source: str | None = None,
        limit: int = 10,
        offset: int = 0,
        include_admin_metadata: bool = False,
    ):
        return self._catalog_service().inspect_source(
            doc_id=doc_id,
            source=source,
            limit=limit,
            offset=offset,
            include_admin_metadata=include_admin_metadata,
        )

    def delete_source(self, *, doc_id: str | None = None, source: str | None = None):
        return self._catalog_service().delete_source(doc_id=doc_id, source=source)

    def reingest_source(self, *, doc_id: str | None = None, source: str | None = None):
        return self._catalog_service().reingest_source(doc_id=doc_id, source=source)

    def _ingest_service(self) -> IngestService:
        if self.ingest_service is None:
            self.ingest_service = IngestService()
        return self.ingest_service

    def _catalog_service(self) -> CatalogService:
        if self.catalog_service is None:
            self.catalog_service = CatalogService(ingest_service=self._ingest_service())
        return self.catalog_service


@dataclass
class SkillOrchestrator:
    """Controlled entrypoint for the skill system."""

    skill_registry: SkillRegistry = field(default_factory=get_skill_registry)
    access_evaluator: SkillAccessEvaluator = field(init=False)

    def __post_init__(self) -> None:
        self.access_evaluator = SkillAccessEvaluator(self.skill_registry)

    def list_skills(self) -> tuple[SkillCatalogEntry, ...]:
        return self.skill_registry.catalog()

    def get_skill_detail(self, skill_id: str) -> SkillCatalogDetail | None:
        return self.skill_registry.catalog_detail(skill_id)

    def resolve_plan_skill_bindings(self, request: UnifiedExecutionRequest) -> tuple[SkillAccessDecision, ...]:
        return self.access_evaluator.resolve_requested_skills(
            requested_skill_id=request.requested_skill_id,
            policy=request.skill_policy,
        )

    def execute_skill(
        self,
        *,
        request: SkillInvocationRequest | None = None,
        name: str | None = None,
        arguments: dict[str, object] | None = None,
        invocation_source: SkillInvocationSource = SkillInvocationSource.MANUAL,
        run_id: str | None = None,
        step_id: str | None = None,
        caller_context: dict[str, object] | None = None,
        request_id: str | None = None,
        debug: bool = False,
    ) -> SkillInvocationResult:
        if request is None:
            if name is None:
                raise ValueError("Either request or name must be provided for skill execution.")
            request = SkillInvocationRequest(
                skill_id=name,
                arguments=arguments or {},
                invocation_source=invocation_source,
                run_id=run_id,
                step_id=step_id,
                caller_context=dict(caller_context or {}),
            )
        return self.skill_registry.execute(
            request,
            SkillExecutionContext(request_id=request_id, debug=debug),
        )

    def has_skill(self, name: str) -> bool:
        """Return whether the named skill is registered."""

        return self.skill_registry.get_descriptor(name) is not None


@dataclass
class FrontendFacade:
    """Single frontend-facing facade over the main orchestrators."""

    chat: ChatOrchestrator = field(default_factory=ChatOrchestrator)
    knowledge_base: KnowledgeBaseOrchestrator = field(default_factory=KnowledgeBaseOrchestrator)
    skills: SkillOrchestrator = field(default_factory=SkillOrchestrator)
    runtime_resolver: RuntimeResolver = field(default_factory=get_runtime_resolver)
    runtime_factory: RuntimeFactory = field(default_factory=get_runtime_factory)
    runtime_profile_registry: RuntimeProfileRegistry = field(default_factory=get_runtime_profile_registry)
    artifact_builder: ArtifactBuilder = field(default_factory=ArtifactBuilder)
    run_registry: RunRegistry = field(default_factory=get_run_registry)
    event_projector: EventProjector = field(default_factory=get_event_projector)

    def execute(self, request: UnifiedExecutionRequest) -> UnifiedExecutionResponse:
        """Execute one unified frontend task through planning and capability-aware runtime selection."""

        run = self.execute_run(request)
        if run.error is not None:
            raise run.error
        if run.final_response is None:
            raise RuntimeError("Unified execution run completed without a final response.")
        return run.final_response

    def execute_run(self, request: UnifiedExecutionRequest) -> ExecutionRun:
        """Execute one request while collecting a stable event stream."""

        run = ExecutionRun(
            run_id=build_run_id(),
            request_summary=self._build_request_summary(request),
            status=ExecutionRunStatus.RUNNING,
        )
        self.run_registry.register(run, debug_enabled=request.debug or request.include_events, stream_mode="execute")
        collector = EventCollector(
            run_id=run.run_id,
            task_type=request.task_type.value,
            sink=self.run_registry.make_registry_sink(run.run_id),
        )
        collector.emit(
            kind=ExecutionEventKind.RUN_STARTED,
            payload=RunStartedPayload(request=run.request_summary),
        )

        try:
            skill_bindings = self.skills.resolve_plan_skill_bindings(request)
            plan = self.chat.build_execution_plan_with_skills(
                request,
                planned_skill_ids=tuple(binding.descriptor.skill_id for binding in skill_bindings),
            )
            if self._check_cancellation_requested(run.run_id):
                return self._complete_cancelled_run(run=run, collector=collector)
            collector.emit(
                kind=ExecutionEventKind.PLAN_BUILT,
                payload=PlanBuiltPayload(
                    step_count=len(plan.steps),
                    step_ids=tuple(step.name for step in plan.steps),
                    step_kinds=tuple(step.kind.value for step in plan.steps),
                    requires_runtime=plan.decision.requires_runtime,
                ),
            )
            runtime = None
            runtime_match = None

            if plan.decision.requires_runtime:
                runtime_match = self.runtime_resolver.resolve(
                    RuntimeSelectionRequest(
                        task_type=request.task_type.value,
                        output_mode=request.output_mode.value,
                        citation_policy=request.citation_policy.value,
                        skill_policy=request.skill_policy.mode.value,
                        execution_policy=request.execution_policy,
                        policy=RuntimeSelectionPolicy(
                            require_structured_output=plan.decision.requires_structured_output or request.execution_policy.require_structured_output,
                            require_skill_invocation=request.execution_policy.require_skill_support,
                        ),
                    )
                )
                run.selected_runtime_binding = runtime_match.binding
                self.run_registry.update_selected_runtime(
                    run.run_id,
                    selected_runtime=runtime_match.binding.adapter_kind,
                    selected_profile_id=runtime_match.binding.selected_profile_id,
                    selected_provider_kind=runtime_match.binding.provider_kind,
                )
                runtime = self.runtime_factory.create(runtime_match.binding)
                collector.emit(
                    kind=ExecutionEventKind.METADATA_UPDATED,
                    payload=MetadataUpdatedPayload(reason="runtime_resolved"),
                    metadata_delta=ExecutionMetadataDelta(
                        selected_runtime=runtime_match.binding.adapter_kind,
                        selected_profile_id=runtime_match.binding.selected_profile_id,
                        selected_provider_kind=runtime_match.binding.provider_kind,
                        selected_model_name=runtime_match.binding.model_name,
                    ),
                )
                if self._check_cancellation_requested(run.run_id):
                    return self._complete_cancelled_run(run=run, collector=collector)

            response = self._execute_base_task_with_events(
                request=request,
                plan=plan,
                runtime=runtime,
                collector=collector,
                run_id=run.run_id,
            )
            skill_invocations, skill_artifacts = self._execute_plan_skills_with_events(
                request=request,
                plan=plan,
                skill_bindings=skill_bindings,
                collector=collector,
                artifact_start_index=len(response.artifacts),
                run_id=run.run_id,
            )
            final_artifacts = list(response.artifacts)
            final_artifacts.extend(skill_artifacts)

            selected_runtime = runtime_match.binding.adapter_kind if runtime_match is not None else None
            selected_profile_id = runtime_match.binding.selected_profile_id if runtime_match is not None else None
            selected_provider_kind = runtime_match.binding.provider_kind if runtime_match is not None else None
            selected_model_name = runtime_match.binding.model_name if runtime_match is not None else None
            matched_capabilities = runtime_match.binding.resolved_capabilities.labels() if runtime_match is not None else ()
            steps_executed = tuple(step.kind.value for step in plan.steps)
            artifact_kinds = tuple(artifact.kind.value for artifact in final_artifacts)
            primary_artifact_kind = artifact_kinds[0] if artifact_kinds else None
            search_result_artifact = ArtifactMapper.first_search_results(tuple(final_artifacts))
            skill_artifact_count = sum(1 for artifact in final_artifacts if artifact.kind == ArtifactKind.SKILL_RESULT)
            warnings = response.metadata.warnings
            issues = response.metadata.issues
            metadata = replace(
                response.metadata,
                selected_runtime=selected_runtime,
                selected_profile_id=selected_profile_id,
                selected_provider_kind=selected_provider_kind,
                selected_model_name=selected_model_name,
                runtime_capabilities_matched=matched_capabilities,
                resolved_capabilities=matched_capabilities,
                execution_steps_executed=steps_executed,
                artifact_kinds_returned=artifact_kinds,
                primary_artifact_kind=primary_artifact_kind,
                artifact_count=len(final_artifacts),
                search_result_count=0 if search_result_artifact is None else search_result_artifact.total,
                skill_artifact_count=skill_artifact_count,
                skill_invocations=tuple(
                    SkillInvocation(
                        name=record.name,
                        ok=record.ok,
                        message=record.message,
                        output_preview=record.output_preview,
                    )
                    for record, _ in skill_invocations
                ),
                fallback_used=False if runtime_match is None else runtime_match.binding.fallback_used,
                selection_reason=None if runtime_match is None else runtime_match.binding.selection_reason,
                policy_applied=request.execution_policy.describe(),
            )
            if warnings:
                for warning in warnings:
                    collector.emit(
                        kind=ExecutionEventKind.WARNING_EMITTED,
                        payload=WarningEmittedPayload(message=warning),
                    )
            collector.emit(
                kind=ExecutionEventKind.METADATA_UPDATED,
                payload=MetadataUpdatedPayload(reason="finalized_response"),
                metadata_delta=ExecutionMetadataDelta(
                    selected_runtime=selected_runtime,
                    selected_profile_id=selected_profile_id,
                    selected_provider_kind=selected_provider_kind,
                    selected_model_name=selected_model_name,
                    execution_steps_executed=steps_executed,
                    artifact_kinds_returned=artifact_kinds,
                    artifact_count=len(final_artifacts),
                    partial_failure=metadata.partial_failure,
                    warnings=metadata.warnings,
                    issues=metadata.issues,
                ),
            )
            summary = ExecutionSummary(
                selected_runtime=selected_runtime,
                selected_profile_id=selected_profile_id,
                selected_provider_kind=selected_provider_kind,
                selected_model_name=selected_model_name,
                selected_capabilities=matched_capabilities,
                fallback_used=False if runtime_match is None else runtime_match.binding.fallback_used,
                selection_reason=None if runtime_match is None else runtime_match.binding.selection_reason,
                policy_applied=request.execution_policy.describe(),
                execution_steps_executed=steps_executed,
                skill_invocations=tuple(record for record, _ in skill_invocations),
                artifact_kinds_returned=artifact_kinds,
                primary_artifact_kind=primary_artifact_kind,
                artifact_count=len(final_artifacts),
                search_result_count=0 if search_result_artifact is None else search_result_artifact.total,
                skill_artifact_count=skill_artifact_count,
                warnings=warnings,
                issues=issues,
            )
            participating_sources = load_projected_sources(
                extract_participating_doc_ids(response.citations),
                catalog_service=self.knowledge_base._catalog_service(),
            )
            collector.emit(
                kind=ExecutionEventKind.RUN_COMPLETED,
                payload=RunCompletedPayload(
                    artifact_count=len(final_artifacts),
                    primary_artifact_kind=primary_artifact_kind,
                    partial_failure=metadata.partial_failure,
                    participating_sources=participating_sources,
                ),
            )
            final_events = collector.events
            final_response = UnifiedExecutionResponse(
                task_type=request.task_type,
                artifacts=tuple(final_artifacts),
                citations=response.citations,
                grounded_answer=response.grounded_answer,
                compare_result=response.compare_result,
                metadata=metadata if request.include_metadata else metadata,
                execution_summary=summary,
                run_id=run.run_id,
                event_count=len(final_events),
                events=final_events if request.include_events else (),
            )
            run.status = ExecutionRunStatus.COMPLETED
            run.events = final_events
            run.final_response = final_response
            self.run_registry.mark_completed(run.run_id, final_response)
            self.run_registry.record_projected_events(
                run.run_id,
                self.event_projector.project_many(final_events, debug=False),
            )
            return run
        except Exception as exc:
            collector.emit(
                kind=ExecutionEventKind.RUN_FAILED,
                payload=RunFailedPayload(
                    error=exc.__class__.__name__,
                    detail=str(exc),
                ),
                debug_level="debug" if request.debug else "normal",
            )
            run.status = ExecutionRunStatus.FAILED
            run.events = collector.events
            run.error = exc
            self.run_registry.mark_failed(run.run_id, error=exc.__class__.__name__, detail=str(exc))
            self.run_registry.record_projected_events(
                run.run_id,
                self.event_projector.project_many(run.events, debug=False),
            )
            return run

    def execute_chat_request(
        self,
        *,
        query: str,
        top_k: int,
        filters=None,
        runtime_name: str | None = None,
        include_metadata: bool = True,
    ) -> ChatServiceResult:
        """Compatibility entrypoint for legacy chat routes via unified execution."""

        response = self.execute(
            UnifiedExecutionRequest(
                task_type=TaskType.CHAT,
                user_input=query,
                retrieval=RetrievalOptions(top_k=top_k, filters=filters),
                execution_policy=ExecutionPolicy(
                    preferred_profile_id=runtime_name,
                    selection_mode=RuntimeSelectionMode.PREFERRED if runtime_name else RuntimeSelectionMode.AUTO,
                ),
                output_mode=OutputMode.TEXT,
                citation_policy=CitationPolicy.PREFERRED,
                skill_policy=SkillPolicy(),
                include_metadata=include_metadata,
            )
        )
        return ChatServiceResult(
            answer=response.primary_text(),
            citations=list(response.citations),
            grounded_answer=response.grounded_answer,
            metadata=response.metadata,
        )

    def execute_summarize_request(
        self,
        *,
        topic: str,
        top_k: int,
        filters=None,
        mode: str = "basic",
        output_format: str = "text",
        runtime_name: str | None = None,
        include_metadata: bool = True,
    ) -> SummarizeServiceResult:
        """Compatibility entrypoint for legacy summarize routes via unified execution."""

        output_mode = OutputMode.MERMAID if output_format == "mermaid" else OutputMode.TEXT
        response = self.execute(
            UnifiedExecutionRequest(
                task_type=TaskType.SUMMARIZE,
                user_input=topic,
                retrieval=RetrievalOptions(top_k=top_k, filters=filters),
                execution_policy=ExecutionPolicy(
                    preferred_profile_id=runtime_name,
                    selection_mode=RuntimeSelectionMode.PREFERRED if runtime_name else RuntimeSelectionMode.AUTO,
                ),
                output_mode=output_mode,
                citation_policy=CitationPolicy.PREFERRED,
                skill_policy=SkillPolicy(),
                task_options={"mode": mode},
                include_metadata=include_metadata,
            )
        )
        mermaid_block = ArtifactMapper.first_mermaid(response.artifacts)
        return SummarizeServiceResult(
            summary=response.primary_text(),
            citations=list(response.citations),
            grounded_answer=response.grounded_answer,
            metadata=response.metadata,
            structured_output=mermaid_block.mermaid_code if mermaid_block is not None else None,
        )

    def execute_compare_request(
        self,
        *,
        question: str,
        top_k: int,
        filters=None,
        include_metadata: bool = True,
    ) -> CompareServiceResult:
        """Compatibility entrypoint for compare routes via unified execution."""

        response = self.execute(
            UnifiedExecutionRequest(
                task_type=TaskType.COMPARE,
                user_input=question,
                retrieval=RetrievalOptions(top_k=top_k, filters=filters),
                output_mode=OutputMode.STRUCTURED,
                citation_policy=CitationPolicy.PREFERRED,
                skill_policy=SkillPolicy(),
                include_metadata=include_metadata,
            )
        )
        if response.compare_result is None:
            raise RuntimeError("Unified compare execution completed without a compare result.")
        return CompareServiceResult(
            compare_result=response.compare_result,
            citations=list(response.citations),
            metadata=response.metadata,
        )

    def list_runtime_profiles(self):
        """Return safe runtime profile summaries for frontend selectors."""

        return self.runtime_resolver.list_profile_summaries()

    def list_skills(self) -> tuple[SkillCatalogEntry, ...]:
        """Return safe skill catalog summaries for frontend selectors."""

        return self.skills.list_skills()

    def get_skill_detail(self, skill_id: str) -> SkillCatalogDetail | None:
        """Return one safe skill catalog detail entry."""

        return self.skills.get_skill_detail(skill_id)

    def _build_request_summary(self, request: UnifiedExecutionRequest) -> ExecutionRequestSummary:
        preview = request.user_input.strip()
        if len(preview) > 80:
            preview = f"{preview[:77]}..."
        return ExecutionRequestSummary(
            task_type=request.task_type.value,
            user_input_preview=preview,
            output_mode=request.output_mode.value,
            top_k=request.retrieval.top_k,
            citation_policy=request.citation_policy.value,
            skill_policy=request.skill_policy.mode.value,
        )

    def _execute_base_task_with_events(
        self,
        *,
        request: UnifiedExecutionRequest,
        plan: ExecutionPlan,
        runtime: GenerationRuntime | None,
        collector: EventCollector,
        run_id: str,
    ) -> UnifiedExecutionResponse:
        base_steps = [step for step in plan.steps if step.kind != StepKind.SKILL_INVOKE]
        for step in base_steps:
            if self._check_cancellation_requested(run_id):
                raise RuntimeError(f"Execution cancelled before step '{step.name}'.")
            collector.emit(
                kind=ExecutionEventKind.STEP_STARTED,
                step_id=step.name,
                payload=StepStartedPayload(step_name=step.name, step_kind=step.kind.value),
            )

        # Shared retrieval: run the unified pipeline once for CHAT and SUMMARIZE.
        # For SEARCH, the service handles retrieval directly.
        # For COMPARE, the CompareService has its own internal retrieval pipeline
        # and is tested with a fake collection — we skip the unified pipeline to
        # avoid the real search service interfering with test fixtures.
        precomputed_retrieval_state: dict | None = None
        if request.task_type in (TaskType.CHAT, TaskType.SUMMARIZE):
            pipeline = self.chat._retrieval_pipeline()

            def _emit_pipeline_event(payload: RetrievalPipelineProgressPayload | RetrievalPipelineCompletedPayload):
                from app.application.events import RetrievalPipelineCompletedPayload as _Completed
                if isinstance(payload, _Completed):
                    collector.emit(
                        kind=ExecutionEventKind.RETRIEVAL_PIPELINE_COMPLETED,
                        step_id="retrieval_pipeline",
                        payload=payload,
                    )
                else:
                    stage_to_kind = {
                        "retrieval_started": ExecutionEventKind.RETRIEVAL_STARTED,
                        "retrieval_completed": ExecutionEventKind.RETRIEVAL_COMPLETED,
                        "rerank_completed": ExecutionEventKind.RERANK_COMPLETED,
                        "compress_completed": ExecutionEventKind.COMPRESS_COMPLETED,
                    }
                    kind = stage_to_kind.get(payload.stage)
                    if kind:
                        collector.emit(kind=kind, step_id="retrieval_pipeline", payload=payload)

            pipeline_state = pipeline.run(
                query=request.user_input,
                top_k=request.retrieval.top_k,
                filters=request.retrieval.filters,
                event_emitter=_emit_pipeline_event,
            )
            precomputed_retrieval_state = pipeline_state

        if request.task_type == TaskType.CHAT:
            result = self.chat.run_chat_with_runtime(
                request=request,
                runtime=runtime,
                precomputed_hits=precomputed_retrieval_state["hits"] if precomputed_retrieval_state else None,
            )
            response = self._build_chat_response(request=request, result=result)
        elif request.task_type == TaskType.SUMMARIZE:
            result = self.chat.run_summarize_with_runtime(
                request=request,
                runtime=runtime,
                precomputed_hits=precomputed_retrieval_state["hits"] if precomputed_retrieval_state else None,
            )
            response = self._build_summarize_response(request=request, result=result)
        elif request.task_type == TaskType.SEARCH:
            result = self.chat.search(
                query=request.user_input,
                top_k=request.retrieval.top_k,
                filters=request.retrieval.filters,
            )
            response = self._build_search_response(request=request, result=result)
        elif request.task_type == TaskType.COMPARE:
            result = self.chat.compare(
                question=request.user_input,
                top_k=request.retrieval.top_k,
                filters=request.retrieval.filters,
                precomputed_hits=None,  # CompareService has its own internal retrieval
            )
            response = self._build_compare_response(request=request, result=result)
        else:
            raise UnsupportedExecutionModeError(detail=f"Task type '{request.task_type.value}' is not supported yet.")

        for step in base_steps:
            collector.emit(
                kind=ExecutionEventKind.STEP_COMPLETED,
                step_id=step.name,
                payload=StepCompletedPayload(step_name=step.name, step_kind=step.kind.value),
            )

        for index, artifact in enumerate(response.artifacts, start=1):
            collector.emit(
                kind=ExecutionEventKind.ARTIFACT_EMITTED,
                payload=ArtifactEmittedPayload(artifact=artifact, artifact_index=index),
                step_id=artifact.source_step_id,
            )
        return response

    def _execute_plan_skills_with_events(
        self,
        *,
        request: UnifiedExecutionRequest,
        plan: ExecutionPlan,
        skill_bindings: tuple[SkillAccessDecision, ...],
        collector: EventCollector,
        artifact_start_index: int,
        run_id: str,
    ) -> tuple[list[tuple[SkillInvocationRecord, SkillInvocationResult]], list]:
        if request.skill_policy.mode == SkillPolicyMode.DISABLED:
            return [], []

        binding_by_skill = {binding.descriptor.skill_id: binding for binding in skill_bindings}
        results: list[tuple[SkillInvocationRecord, SkillInvocationResult]] = []
        artifacts: list = []
        artifact_index = artifact_start_index
        for step in plan.steps:
            if step.kind != StepKind.SKILL_INVOKE:
                continue
            if self._check_cancellation_requested(run_id):
                raise RuntimeError(f"Execution cancelled before step '{step.name}'.")
            collector.emit(
                kind=ExecutionEventKind.STEP_STARTED,
                step_id=step.name,
                payload=StepStartedPayload(step_name=step.name, step_kind=step.kind.value),
            )
            skill_name = str(step.metadata.get("skill_name") or step.name)
            binding = binding_by_skill.get(skill_name)
            if binding is None:
                raise SkillNotAllowedError(detail=f"Skill '{skill_name}' is not allowed by the active skill policy.")
            if not self.skills.has_skill(skill_name):
                raise SkillNotAllowedError(detail=f"Skill '{skill_name}' is not registered.")
            skill_arguments = dict(request.requested_skill_arguments)
            if not skill_arguments:
                skill_arguments = {"text": request.user_input}
            skill_result = self.skills.execute_skill(
                request=SkillInvocationRequest(
                    skill_id=skill_name,
                    arguments=skill_arguments,
                    invocation_source=binding.invocation_source,
                    run_id=run_id,
                    step_id=step.name,
                    caller_context={
                        "task_type": request.task_type.value,
                        "user_input": request.user_input,
                    },
                ),
                request_id=str(request.conversation_metadata.get("request_id") or "") or None,
                debug=request.debug,
            )
            if not skill_result.success:
                raise SkillExecutionFailedError(detail=f"Skill '{skill_name}' failed during execution.")
            preview = str(
                skill_result.output.get("text")
                or skill_result.output.get("normalized_text")
                or skill_result.summary_text
                or skill_result.message
                or ""
            ).strip() or None
            artifact = self.artifact_builder.build_skill_artifact(skill_result, source_step_id=step.name)
            artifact_index += 1
            results.append(
                (
                    SkillInvocationRecord(
                        name=skill_result.skill_id,
                        ok=skill_result.success,
                        message=skill_result.summary_text or skill_result.message,
                        output_preview=preview,
                    ),
                    skill_result,
                )
            )
            artifacts.append(artifact)
            collector.emit(
                kind=ExecutionEventKind.ARTIFACT_EMITTED,
                payload=ArtifactEmittedPayload(artifact=artifact, artifact_index=artifact_index),
                step_id=step.name,
            )
            collector.emit(
                kind=ExecutionEventKind.STEP_COMPLETED,
                step_id=step.name,
                payload=StepCompletedPayload(step_name=step.name, step_kind=step.kind.value),
            )
        return results, artifacts

    def _check_cancellation_requested(self, run_id: str) -> bool:
        return self.run_registry.is_cancellation_requested(run_id)

    def _complete_cancelled_run(self, *, run: ExecutionRun, collector: EventCollector) -> ExecutionRun:
        collector.emit(
            kind=ExecutionEventKind.WARNING_EMITTED,
            payload=WarningEmittedPayload(message="Cancellation requested; execution stopped at a safe boundary."),
        )
        collector.emit(
            kind=ExecutionEventKind.RUN_FAILED,
            payload=RunFailedPayload(error="CancelledError", detail="Execution cancelled before completion."),
        )
        run.status = ExecutionRunStatus.CANCELLED
        run.events = collector.events
        run.error = RuntimeError("Execution cancelled before completion.")
        self.run_registry.mark_cancelled(run.run_id, detail="Execution cancelled before completion.")
        self.run_registry.record_projected_events(
            run.run_id,
            self.event_projector.project_many(run.events, debug=False),
        )
        return run

    def _build_chat_response(
        self,
        *,
        request: UnifiedExecutionRequest,
        result: ChatServiceResult,
    ) -> UnifiedExecutionResponse:
        return UnifiedExecutionResponse(
            task_type=request.task_type,
            artifacts=self.artifact_builder.build_chat_artifacts(result),
            citations=tuple(result.citations),
            grounded_answer=result.grounded_answer,
            metadata=result.metadata,
        )

    def _build_summarize_response(
        self,
        *,
        request: UnifiedExecutionRequest,
        result: SummarizeServiceResult,
    ) -> UnifiedExecutionResponse:
        return UnifiedExecutionResponse(
            task_type=request.task_type,
            artifacts=self.artifact_builder.build_summarize_artifacts(result, output_mode=request.output_mode.value),
            citations=tuple(result.citations),
            grounded_answer=result.grounded_answer,
            metadata=result.metadata,
        )

    def _build_search_response(
        self,
        *,
        request: UnifiedExecutionRequest,
        result,
    ) -> UnifiedExecutionResponse:
        citations = tuple(hit.citation for hit in result.hits)
        return UnifiedExecutionResponse(
            task_type=request.task_type,
            artifacts=self.artifact_builder.build_search_artifacts(result),
            citations=citations,
            metadata=result.metadata,
        )

    def _build_compare_response(
        self,
        *,
        request: UnifiedExecutionRequest,
        result: CompareServiceResult,
    ) -> UnifiedExecutionResponse:
        return UnifiedExecutionResponse(
            task_type=request.task_type,
            artifacts=self.artifact_builder.build_compare_artifacts(result),
            citations=tuple(result.citations),
            compare_result=result.compare_result,
            metadata=result.metadata,
        )
