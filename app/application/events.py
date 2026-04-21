"""Application-facing execution event contract and in-memory collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from app.application.artifacts import BaseArtifact
from app.runtime.models import ResolvedRuntimeBinding
from app.services.service_models import ServiceIssue

if TYPE_CHECKING:
    from app.application.models import UnifiedExecutionResponse


class ExecutionEventKind(StrEnum):
    """Stable event kinds for future streaming and progress UIs."""

    RUN_STARTED = "run_started"
    PLAN_BUILT = "plan_built"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    ARTIFACT_EMITTED = "artifact_emitted"
    WARNING_EMITTED = "warning_emitted"
    METADATA_UPDATED = "metadata_updated"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    # Retrieval pipeline trace events
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    RERANK_COMPLETED = "rerank_completed"
    COMPRESS_COMPLETED = "compress_completed"
    RETRIEVAL_PIPELINE_COMPLETED = "retrieval_pipeline_completed"


class ExecutionRunStatus(StrEnum):
    """Lifecycle status of one unified execution run."""

    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ExecutionRequestSummary:
    """Lightweight request summary attached to an execution run."""

    task_type: str
    user_input_preview: str
    output_mode: str
    top_k: int
    citation_policy: str
    skill_policy: str


@dataclass(frozen=True)
class RunStartedPayload:
    """Payload emitted when a run begins."""

    request: ExecutionRequestSummary


@dataclass(frozen=True)
class PlanBuiltPayload:
    """Payload emitted after a plan is built."""

    step_count: int
    step_ids: tuple[str, ...]
    step_kinds: tuple[str, ...]
    requires_runtime: bool


@dataclass(frozen=True)
class StepStartedPayload:
    """Payload emitted when a logical step starts."""

    step_name: str
    step_kind: str


@dataclass(frozen=True)
class StepCompletedPayload:
    """Payload emitted when a logical step completes."""

    step_name: str
    step_kind: str
    status: str = "completed"


@dataclass(frozen=True)
class ArtifactEmittedPayload:
    """Payload emitted when one artifact is produced."""

    artifact: BaseArtifact
    artifact_index: int


@dataclass(frozen=True)
class WarningEmittedPayload:
    """Payload emitted for warnings surfaced during execution."""

    message: str
    code: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class ExecutionMetadataDelta:
    """Controlled metadata delta emitted during run updates."""

    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    selected_model_name: str | None = None
    execution_steps_executed: tuple[str, ...] = ()
    artifact_kinds_returned: tuple[str, ...] = ()
    artifact_count: int = 0
    partial_failure: bool | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[ServiceIssue, ...] = ()


@dataclass(frozen=True)
class MetadataUpdatedPayload:
    """Payload emitted when metadata is incrementally refined."""

    reason: str


@dataclass(frozen=True)
class RunCompletedPayload:
    """Payload emitted when a run completes successfully."""

    artifact_count: int
    primary_artifact_kind: str | None = None
    partial_failure: bool = False


@dataclass(frozen=True)
class RunFailedPayload:
    """Payload emitted when a run fails."""

    error: str
    detail: str
    failed_step_id: str | None = None


@dataclass(frozen=True)
class RetrievalPipelineProgressPayload:
    """Payload emitted for each retrieval pipeline stage completion."""

    stage: str  # one of: retrieval_started, retrieval_completed, rerank_completed, compress_completed
    retrieved_hits: int = 0
    reranked_hits: int = 0
    compressed_hits: int = 0


@dataclass(frozen=True)
class RetrievalPipelineCompletedPayload:
    """Payload emitted when the entire retrieval pipeline finishes."""

    retrieved_hits: int = 0
    reranked_hits: int = 0
    compressed_hits: int = 0
    total_ms: float = 0.0


ExecutionEventPayload = (
    RunStartedPayload
    | PlanBuiltPayload
    | StepStartedPayload
    | StepCompletedPayload
    | ArtifactEmittedPayload
    | WarningEmittedPayload
    | MetadataUpdatedPayload
    | RunCompletedPayload
    | RunFailedPayload
    | RetrievalPipelineProgressPayload
    | RetrievalPipelineCompletedPayload
)


@dataclass(frozen=True)
class ExecutionEvent:
    """One typed execution event."""

    event_id: str
    run_id: str
    sequence: int
    kind: ExecutionEventKind
    timestamp: str
    task_type: str
    step_id: str | None = None
    payload: ExecutionEventPayload | None = None
    metadata_delta: ExecutionMetadataDelta | None = None
    visibility: str = "public"
    debug_level: str = "normal"


class ExecutionEventSink(Protocol):
    """Protocol for receiving execution events."""

    def emit(self, event: ExecutionEvent) -> None:
        ...


@dataclass
class InMemoryExecutionEventSink:
    """Simple in-memory sink used by default in non-streaming mode."""

    events: list[ExecutionEvent] = field(default_factory=list)

    def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


@dataclass
class StreamingExecutionEventSink:
    """Placeholder sink for future SSE/WebSocket adapters."""

    def emit(self, event: ExecutionEvent) -> None:  # pragma: no cover - placeholder
        raise NotImplementedError("Streaming execution event sink is not implemented yet.")


@dataclass
class EventCollector:
    """Build and collect stable execution events for one run."""

    run_id: str
    task_type: str
    sink: ExecutionEventSink = field(default_factory=InMemoryExecutionEventSink)
    _sequence: int = 0

    def emit(
        self,
        *,
        kind: ExecutionEventKind,
        payload: ExecutionEventPayload | None = None,
        step_id: str | None = None,
        metadata_delta: ExecutionMetadataDelta | None = None,
        visibility: str = "public",
        debug_level: str = "normal",
    ) -> ExecutionEvent:
        self._sequence += 1
        event = ExecutionEvent(
            event_id=f"evt-{self._sequence}",
            run_id=self.run_id,
            sequence=self._sequence,
            kind=kind,
            timestamp=datetime.now(timezone.utc).isoformat(),
            task_type=self.task_type,
            step_id=step_id,
            payload=payload,
            metadata_delta=metadata_delta,
            visibility=visibility,
            debug_level=debug_level,
        )
        self.sink.emit(event)
        return event

    @property
    def events(self) -> tuple[ExecutionEvent, ...]:
        sink_events = getattr(self.sink, "events", None)
        if sink_events is None:
            return ()
        return tuple(sink_events)


@dataclass
class ExecutionRun:
    """Collected state for one unified execution run."""

    run_id: str
    request_summary: ExecutionRequestSummary
    status: ExecutionRunStatus = ExecutionRunStatus.PENDING
    selected_runtime_binding: ResolvedRuntimeBinding | None = None
    events: tuple[ExecutionEvent, ...] = ()
    final_response: UnifiedExecutionResponse | None = None
    error: Exception | None = None


def build_run_id() -> str:
    """Create a stable opaque execution run id."""

    return f"run-{uuid4().hex[:12]}"
