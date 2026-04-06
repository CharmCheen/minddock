"""Unit tests for the transient run control plane."""

from datetime import datetime, timedelta, timezone

from app.application.artifacts import ArtifactKind, TextArtifact
from app.application.client_events import ClientArtifactPayload, ClientEvent, ClientEventChannel, ClientEventKind, EventVisibility
from app.application.events import ExecutionRequestSummary, ExecutionRun, ExecutionRunStatus
from app.application.models import TaskType, UnifiedExecutionResponse
from app.application.run_control import RunControlConfig, RunRegistry


def _registry() -> RunRegistry:
    return RunRegistry(
        config=RunControlConfig(
            max_runs=5,
            recent_event_buffer_size=3,
            completed_run_ttl_seconds=1,
            heartbeat_interval_seconds=1,
        )
    )


def _run(run_id: str = "run-1") -> ExecutionRun:
    return ExecutionRun(
        run_id=run_id,
        request_summary=ExecutionRequestSummary(
            task_type="chat",
            user_input_preview="hello",
            output_mode="text",
            top_k=5,
            citation_policy="preferred",
            skill_policy="disabled",
        ),
        status=ExecutionRunStatus.RUNNING,
    )


def test_run_registry_registers_and_returns_status() -> None:
    registry = _registry()
    registry.register(_run())

    stored = registry.get("run-1")

    assert stored is not None
    assert stored.status == ExecutionRunStatus.RUNNING


def test_run_registry_status_transitions_to_completed_and_failed() -> None:
    registry = _registry()
    registry.register(_run("run-complete"))
    registry.register(_run("run-fail"))

    registry.mark_completed(
        "run-complete",
        UnifiedExecutionResponse(
            task_type=TaskType.CHAT,
            artifacts=(TextArtifact(artifact_id="text-1", kind=ArtifactKind.TEXT, text="done"),),
        ),
    )
    registry.mark_failed("run-fail", error="RuntimeError", detail="boom")

    assert registry.get("run-complete").status == ExecutionRunStatus.COMPLETED
    assert registry.get("run-fail").status == ExecutionRunStatus.FAILED


def test_recent_client_events_are_buffered_and_replayed() -> None:
    registry = _registry()
    registry.register(_run())
    for index in range(1, 5):
        registry.append_client_event(
            "run-1",
            ClientEvent(
                event_id=f"evt-{index}",
                run_id="run-1",
                sequence=index,
                kind=ClientEventKind.ARTIFACT,
                channel=ClientEventChannel.ARTIFACT,
                visibility=EventVisibility.PUBLIC,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload=ClientArtifactPayload(
                    artifact=TextArtifact(artifact_id=f"text-{index}", kind=ArtifactKind.TEXT, text=str(index)),
                    artifact_index=index,
                ),
                cursor=f"run-1:{index}",
            ),
        )

    replay = registry.get_recent_client_events("run-1")

    assert len(replay) == 3
    assert replay[0].sequence == 2
    assert replay[-1].sequence == 4


def test_cancellation_request_is_recorded() -> None:
    registry = _registry()
    registry.register(_run())

    registry.request_cancellation("run-1")

    stored = registry.get("run-1")
    assert stored is not None
    assert stored.cancellation_requested is True
    assert stored.status == ExecutionRunStatus.CANCELLING


def test_completed_run_cancel_semantics_remain_completed() -> None:
    registry = _registry()
    registry.register(_run())
    registry.mark_completed("run-1")

    registry.request_cancellation("run-1")

    stored = registry.get("run-1")
    assert stored is not None
    assert stored.cancellation_requested is True
    assert stored.status == ExecutionRunStatus.COMPLETED


def test_expired_runs_are_evicted() -> None:
    registry = _registry()
    registry.register(_run())
    registry.mark_completed("run-1")
    future = datetime.now(timezone.utc) + timedelta(seconds=10)

    evicted = registry.evict_expired_runs(now=future)

    assert evicted == 1
    assert registry.get("run-1") is None
