"""Unit tests for client-facing event projection and visibility policies."""

from app.api.schemas import ClientEventResponseItem
from app.application.artifacts import ArtifactKind, TextArtifact
from app.application.client_events import (
    ClientEventChannel,
    ClientEventKind,
    EventProjector,
    ProgressPhase,
)
from app.application.events import (
    ArtifactEmittedPayload,
    EventCollector,
    ExecutionEventKind,
    ExecutionMetadataDelta,
    MetadataUpdatedPayload,
    PlanBuiltPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    StepCompletedPayload,
    StepStartedPayload,
)


def _collector() -> EventCollector:
    return EventCollector(run_id="run-123", task_type="chat")


def test_internal_execution_event_projects_to_client_event() -> None:
    collector = _collector()
    event = collector.emit(
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

    projected = EventProjector().project(event)

    assert projected is not None
    assert projected.kind == ClientEventKind.RUN_STARTED
    assert projected.channel == ClientEventChannel.SYSTEM


def test_debug_and_public_visibility_are_distinct() -> None:
    collector = _collector()
    event = collector.emit(
        kind=ExecutionEventKind.STEP_COMPLETED,
        payload=StepCompletedPayload(step_name="generate_answer", step_kind="generate"),
    )
    projector = EventProjector()

    assert projector.project(event, debug=False) is None
    debug_event = projector.project(event, debug=True)
    assert debug_event is not None
    assert debug_event.visibility.value == "debug"


def test_internal_steps_map_to_stable_progress_phases() -> None:
    collector = _collector()
    event = collector.emit(
        kind=ExecutionEventKind.STEP_STARTED,
        payload=StepStartedPayload(step_name="retrieve_hits", step_kind="retrieve"),
    )

    projected = EventProjector().project(event)

    assert projected is not None
    assert projected.kind == ClientEventKind.PROGRESS
    assert projected.payload.phase == ProgressPhase.RETRIEVING
    assert projected.payload.status == "started"


def test_artifact_emitted_maps_to_client_artifact_and_reuses_artifact_shape() -> None:
    collector = _collector()
    event = collector.emit(
        kind=ExecutionEventKind.ARTIFACT_EMITTED,
        payload=ArtifactEmittedPayload(
            artifact=TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello"),
            artifact_index=1,
        ),
    )

    projected = EventProjector().project(event)
    outward = ClientEventResponseItem.from_client_event(projected)

    assert projected is not None
    assert projected.kind == ClientEventKind.ARTIFACT
    assert outward.payload["artifact"]["kind"] == "text"
    assert outward.payload["artifact"]["content"]["text"] == "hello"


def test_metadata_updated_does_not_leak_raw_delta_in_public_stream() -> None:
    collector = _collector()
    event = collector.emit(
        kind=ExecutionEventKind.METADATA_UPDATED,
        payload=MetadataUpdatedPayload(reason="runtime_resolved"),
        metadata_delta=ExecutionMetadataDelta(selected_profile_id="secret_profile"),
    )

    projected = EventProjector().project(event)
    outward = ClientEventResponseItem.from_client_event(projected)

    assert projected is not None
    assert projected.kind == ClientEventKind.PROGRESS
    assert outward.payload["phase"] == "resolving_runtime"
    assert "selected_profile_id" not in outward.payload


def test_failed_execution_projects_to_failed_client_event() -> None:
    collector = _collector()
    event = collector.emit(
        kind=ExecutionEventKind.RUN_FAILED,
        payload=RunFailedPayload(error="RuntimeError", detail="boom"),
    )

    projected = EventProjector().project(event)

    assert projected is not None
    assert projected.kind == ClientEventKind.FAILED
    assert projected.payload.detail == "boom"


def test_projection_sequence_is_stable_for_public_stream() -> None:
    collector = _collector()
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
        kind=ExecutionEventKind.ARTIFACT_EMITTED,
        payload=ArtifactEmittedPayload(
            artifact=TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="hello"),
            artifact_index=1,
        ),
    )
    collector.emit(
        kind=ExecutionEventKind.RUN_COMPLETED,
        payload=RunCompletedPayload(artifact_count=1, primary_artifact_kind="text"),
    )

    projected = EventProjector().project_many(collector.events, debug=False)

    assert [event.kind.value for event in projected] == ["run_started", "progress", "artifact", "completed"]
