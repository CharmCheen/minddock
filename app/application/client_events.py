"""Client-facing event contract projected from internal execution events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.artifacts import BaseArtifact
from app.application.events import (
    ArtifactEmittedPayload,
    ExecutionEvent,
    ExecutionEventKind,
    MetadataUpdatedPayload,
    PlanBuiltPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    StepCompletedPayload,
    StepStartedPayload,
    WarningEmittedPayload,
)
from app.rag.source_models import SourceCatalogEntry


class ClientEventKind(StrEnum):
    """Stable client-facing event kinds."""

    RUN_STARTED = "run_started"
    PROGRESS = "progress"
    ARTIFACT = "artifact"
    WARNING = "warning"
    HEARTBEAT = "heartbeat"
    COMPLETED = "completed"
    FAILED = "failed"
    INFO = "info"


class ClientEventChannel(StrEnum):
    """High-level client event channels."""

    PROGRESS = "progress"
    ARTIFACT = "artifact"
    DIAGNOSTIC = "diagnostic"
    SYSTEM = "system"


class EventVisibility(StrEnum):
    """Visibility level for client events."""

    PUBLIC = "public"
    DEBUG = "debug"
    INTERNAL = "internal"


class ProgressPhase(StrEnum):
    """Stable progress phases exposed to the frontend."""

    PREPARING = "preparing"
    RESOLVING_RUNTIME = "resolving_runtime"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    FORMATTING = "formatting"
    INVOKING_SKILL = "invoking_skill"
    FINALIZING = "finalizing"


@dataclass(frozen=True)
class ClientRunStartedPayload:
    """Public payload for run start."""

    task_type: str
    output_mode: str


@dataclass(frozen=True)
class ClientProgressPayload:
    """Stable progress update for frontend consumption."""

    phase: ProgressPhase
    status: str
    message: str | None = None


@dataclass(frozen=True)
class ClientArtifactPayload:
    """Artifact payload surfaced to client subscribers."""

    artifact: BaseArtifact
    artifact_index: int


@dataclass(frozen=True)
class ClientWarningPayload:
    """Client-facing warning payload."""

    message: str


@dataclass(frozen=True)
class ClientHeartbeatPayload:
    """Client-facing heartbeat payload."""

    message: str = "keepalive"


@dataclass(frozen=True)
class ClientCompletedPayload:
    """Client-facing completion payload."""

    artifact_count: int
    primary_artifact_kind: str | None = None
    partial_failure: bool = False
    participating_sources: tuple[SourceCatalogEntry, ...] = ()


@dataclass(frozen=True)
class ClientFailedPayload:
    """Client-facing failure payload."""

    error: str
    detail: str


ClientEventPayload = (
    ClientRunStartedPayload
    | ClientProgressPayload
    | ClientArtifactPayload
    | ClientWarningPayload
    | ClientHeartbeatPayload
    | ClientCompletedPayload
    | ClientFailedPayload
)


@dataclass(frozen=True)
class ClientEvent:
    """Projected client-facing event."""

    event_id: str
    run_id: str
    sequence: int
    kind: ClientEventKind
    channel: ClientEventChannel
    visibility: EventVisibility
    timestamp: str
    payload: ClientEventPayload
    cursor: str


@dataclass(frozen=True)
class EventVisibilityPolicy:
    """Controls whether projected events are visible for a stream mode."""

    def allows(self, visibility: EventVisibility, *, debug: bool) -> bool:
        if visibility == EventVisibility.INTERNAL:
            return False
        if visibility == EventVisibility.DEBUG:
            return debug
        return True


@dataclass(frozen=True)
class EventChannelPolicy:
    """Maps client events onto stable channels."""

    def channel_for(self, kind: ClientEventKind) -> ClientEventChannel:
        if kind == ClientEventKind.ARTIFACT:
            return ClientEventChannel.ARTIFACT
        if kind == ClientEventKind.WARNING:
            return ClientEventChannel.DIAGNOSTIC
        if kind in {ClientEventKind.RUN_STARTED, ClientEventKind.COMPLETED, ClientEventKind.FAILED, ClientEventKind.INFO, ClientEventKind.HEARTBEAT}:
            return ClientEventChannel.SYSTEM
        return ClientEventChannel.PROGRESS


@dataclass(frozen=True)
class EventProjector:
    """Project internal execution events into a smaller client-facing contract."""

    visibility_policy: EventVisibilityPolicy = EventVisibilityPolicy()
    channel_policy: EventChannelPolicy = EventChannelPolicy()

    def project(self, event: ExecutionEvent, *, debug: bool = False) -> ClientEvent | None:
        projected = self._project_internal_event(event)
        if projected is None:
            return None
        if not self.visibility_policy.allows(projected.visibility, debug=debug):
            return None
        return projected

    def project_many(self, events: tuple[ExecutionEvent, ...], *, debug: bool = False) -> tuple[ClientEvent, ...]:
        output: list[ClientEvent] = []
        for event in events:
            projected = self.project(event, debug=debug)
            if projected is not None:
                output.append(projected)
        return tuple(output)

    def _project_internal_event(self, event: ExecutionEvent) -> ClientEvent | None:
        visibility = EventVisibility.PUBLIC if str(event.visibility) == "public" else EventVisibility.DEBUG

        if event.kind == ExecutionEventKind.RUN_STARTED:
            payload = self._require_payload(event, RunStartedPayload)
            return self._client_event(
                event=event,
                kind=ClientEventKind.RUN_STARTED,
                visibility=visibility,
                payload=ClientRunStartedPayload(
                    task_type=payload.request.task_type,
                    output_mode=payload.request.output_mode,
                ),
            )

        if event.kind == ExecutionEventKind.PLAN_BUILT:
            payload = self._require_payload(event, PlanBuiltPayload)
            return self._client_event(
                event=event,
                kind=ClientEventKind.PROGRESS,
                visibility=EventVisibility.PUBLIC,
                payload=ClientProgressPayload(
                    phase=ProgressPhase.PREPARING,
                    status="completed",
                    message=f"execution plan ready ({payload.step_count} steps)",
                ),
            )

        if event.kind == ExecutionEventKind.STEP_STARTED:
            payload = self._require_payload(event, StepStartedPayload)
            phase = self._phase_for_step_kind(payload.step_kind)
            if phase is None:
                return None
            return self._client_event(
                event=event,
                kind=ClientEventKind.PROGRESS,
                visibility=EventVisibility.PUBLIC,
                payload=ClientProgressPayload(phase=phase, status="started"),
            )

        if event.kind == ExecutionEventKind.STEP_COMPLETED:
            payload = self._require_payload(event, StepCompletedPayload)
            phase = self._phase_for_step_kind(payload.step_kind)
            if phase is None:
                return None
            return self._client_event(
                event=event,
                kind=ClientEventKind.PROGRESS,
                visibility=EventVisibility.DEBUG,
                payload=ClientProgressPayload(phase=phase, status=payload.status),
            )

        if event.kind == ExecutionEventKind.ARTIFACT_EMITTED:
            payload = self._require_payload(event, ArtifactEmittedPayload)
            return self._client_event(
                event=event,
                kind=ClientEventKind.ARTIFACT,
                visibility=EventVisibility.PUBLIC,
                payload=ClientArtifactPayload(artifact=payload.artifact, artifact_index=payload.artifact_index),
            )

        if event.kind == ExecutionEventKind.WARNING_EMITTED:
            payload = self._require_payload(event, WarningEmittedPayload)
            return self._client_event(
                event=event,
                kind=ClientEventKind.WARNING,
                visibility=EventVisibility.PUBLIC,
                payload=ClientWarningPayload(message=payload.message),
            )

        if event.kind == ExecutionEventKind.METADATA_UPDATED:
            payload = self._require_payload(event, MetadataUpdatedPayload)
            phase = self._phase_for_metadata_reason(payload.reason)
            if phase is None:
                return None
            return self._client_event(
                event=event,
                kind=ClientEventKind.PROGRESS,
                visibility=EventVisibility.PUBLIC,
                payload=ClientProgressPayload(phase=phase, status="completed"),
            )

        if event.kind == ExecutionEventKind.RUN_COMPLETED:
            payload = self._require_payload(event, RunCompletedPayload)
            return self._client_event(
                event=event,
                kind=ClientEventKind.COMPLETED,
                visibility=EventVisibility.PUBLIC,
                payload=ClientCompletedPayload(
                    artifact_count=payload.artifact_count,
                    primary_artifact_kind=payload.primary_artifact_kind,
                    partial_failure=payload.partial_failure,
                    participating_sources=payload.participating_sources,
                ),
            )

        if event.kind == ExecutionEventKind.RUN_FAILED:
            payload = self._require_payload(event, RunFailedPayload)
            return self._client_event(
                event=event,
                kind=ClientEventKind.FAILED,
                visibility=EventVisibility.PUBLIC,
                payload=ClientFailedPayload(error=payload.error, detail=payload.detail),
            )

        return None

    def _client_event(
        self,
        *,
        event: ExecutionEvent,
        kind: ClientEventKind,
        visibility: EventVisibility,
        payload: ClientEventPayload,
    ) -> ClientEvent:
        return ClientEvent(
            event_id=event.event_id,
            run_id=event.run_id,
            sequence=event.sequence,
            kind=kind,
            channel=self.channel_policy.channel_for(kind),
            visibility=visibility,
            timestamp=event.timestamp,
            payload=payload,
            cursor=f"{event.run_id}:{event.sequence}",
        )

    @staticmethod
    def _phase_for_step_kind(step_kind: str) -> ProgressPhase | None:
        if step_kind in {"retrieve", "rerank", "compress"}:
            return ProgressPhase.RETRIEVING
        if step_kind in {"generate", "summarize_map", "summarize_reduce"}:
            return ProgressPhase.GENERATING
        if step_kind == "format_output":
            return ProgressPhase.FORMATTING
        if step_kind == "skill_invoke":
            return ProgressPhase.INVOKING_SKILL
        return None

    @staticmethod
    def _phase_for_metadata_reason(reason: str) -> ProgressPhase | None:
        if reason == "runtime_resolved":
            return ProgressPhase.RESOLVING_RUNTIME
        if reason == "finalized_response":
            return ProgressPhase.FINALIZING
        return None

    @staticmethod
    def _require_payload(event: ExecutionEvent, expected_type):
        payload = event.payload
        if not isinstance(payload, expected_type):
            raise TypeError(f"Execution event '{event.kind.value}' did not contain expected payload '{expected_type.__name__}'.")
        return payload


def get_event_projector() -> EventProjector:
    """Return the default client-event projector."""

    return EventProjector()
