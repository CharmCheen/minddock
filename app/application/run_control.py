"""Transient in-memory run control plane for unified execution runs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from threading import RLock

from app.application.client_events import ClientEvent, EventProjector, get_event_projector
from app.application.events import ExecutionEvent, ExecutionEventSink, ExecutionRun, ExecutionRunStatus
from app.application.models import UnifiedExecutionResponse
from app.core.config import get_settings


@dataclass(frozen=True)
class RunControlConfig:
    """Transient run control configuration."""

    max_runs: int = 100
    recent_event_buffer_size: int = 100
    completed_run_ttl_seconds: int = 300
    heartbeat_interval_seconds: int = 5


@dataclass(frozen=True)
class RunErrorSummary:
    """Minimal stable error summary attached to a managed run."""

    error: str
    detail: str


@dataclass
class ManagedRun:
    """In-memory managed run record."""

    run_id: str
    request_summary: object
    status: ExecutionRunStatus
    created_at: datetime
    updated_at: datetime
    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    internal_events: list[ExecutionEvent] = field(default_factory=list)
    recent_client_events: deque[ClientEvent] = field(default_factory=deque)
    final_response: UnifiedExecutionResponse | None = None
    error_summary: RunErrorSummary | None = None
    cancellation_requested: bool = False
    debug_enabled: bool = False
    stream_mode: str | None = None
    expires_at: datetime | None = None

    @property
    def event_count(self) -> int:
        return len(self.recent_client_events)

    @property
    def has_final_response(self) -> bool:
        return self.final_response is not None


@dataclass
class RunRegistryMirroringSink:
    """Execution event sink that mirrors internal events into the run registry."""

    registry: "RunRegistry"
    run_id: str
    events: list[ExecutionEvent] = field(default_factory=list)

    def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)
        self.registry.append_internal_event(self.run_id, event)


@dataclass
class RunRegistry:
    """Transient in-memory registry for managed execution runs."""

    config: RunControlConfig
    projector: EventProjector = field(default_factory=get_event_projector)
    _runs: dict[str, ManagedRun] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def register(self, run: ExecutionRun, *, debug_enabled: bool = False, stream_mode: str | None = None) -> ManagedRun:
        with self._lock:
            self.evict_expired_runs()
            now = self._now()
            managed = ManagedRun(
                run_id=run.run_id,
                request_summary=run.request_summary,
                status=run.status,
                created_at=now,
                updated_at=now,
                debug_enabled=debug_enabled,
                stream_mode=stream_mode,
                recent_client_events=deque(maxlen=self.config.recent_event_buffer_size),
            )
            self._runs[run.run_id] = managed
            self._enforce_max_runs()
            return managed

    def get(self, run_id: str) -> ManagedRun | None:
        with self._lock:
            self.evict_expired_runs()
            return self._runs.get(run_id)

    def update_status(self, run_id: str, status: ExecutionRunStatus) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.status = status
            run.updated_at = self._now()
            return run

    def append_client_event(self, run_id: str, event: ClientEvent) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.recent_client_events.append(event)
            run.updated_at = self._now()
            return run

    def append_internal_event(self, run_id: str, event: ExecutionEvent) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.internal_events.append(event)
            run.updated_at = self._now()
            return run

    def update_selected_runtime(
        self,
        run_id: str,
        *,
        selected_runtime: str | None,
        selected_profile_id: str | None,
        selected_provider_kind: str | None,
    ) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.selected_runtime = selected_runtime
            run.selected_profile_id = selected_profile_id
            run.selected_provider_kind = selected_provider_kind
            run.updated_at = self._now()
            return run

    def mark_completed(self, run_id: str, final_response: UnifiedExecutionResponse | None = None) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.status = ExecutionRunStatus.COMPLETED
            run.updated_at = self._now()
            run.final_response = final_response
            run.expires_at = run.updated_at + timedelta(seconds=self.config.completed_run_ttl_seconds)
            return run

    def mark_failed(self, run_id: str, *, error: str, detail: str) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.status = ExecutionRunStatus.FAILED
            run.updated_at = self._now()
            run.error_summary = RunErrorSummary(error=error, detail=detail)
            run.expires_at = run.updated_at + timedelta(seconds=self.config.completed_run_ttl_seconds)
            return run

    def mark_cancelled(self, run_id: str, *, detail: str) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.status = ExecutionRunStatus.CANCELLED
            run.updated_at = self._now()
            run.error_summary = RunErrorSummary(error="CancelledError", detail=detail)
            run.expires_at = run.updated_at + timedelta(seconds=self.config.completed_run_ttl_seconds)
            return run

    def request_cancellation(self, run_id: str) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.cancellation_requested = True
            if run.status == ExecutionRunStatus.RUNNING:
                run.status = ExecutionRunStatus.CANCELLING
            run.updated_at = self._now()
            return run

    def is_cancellation_requested(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            return False if run is None else run.cancellation_requested

    def get_recent_client_events(self, run_id: str, *, debug: bool = False) -> tuple[ClientEvent, ...]:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return ()
            if debug:
                return self.projector.project_many(tuple(run.internal_events), debug=True)
            return tuple(run.recent_client_events)

    def record_projected_events(self, run_id: str, events: tuple[ClientEvent, ...]) -> ManagedRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            for event in events:
                run.recent_client_events.append(event)
            run.updated_at = self._now()
            return run

    def evict_expired_runs(self, *, now: datetime | None = None) -> int:
        with self._lock:
            current = now or self._now()
            expired_ids = [
                run_id
                for run_id, run in self._runs.items()
                if run.expires_at is not None and current >= run.expires_at
            ]
            for run_id in expired_ids:
                run = self._runs[run_id]
                run.status = ExecutionRunStatus.EXPIRED
                del self._runs[run_id]
            return len(expired_ids)

    def make_registry_sink(self, run_id: str) -> ExecutionEventSink:
        return RunRegistryMirroringSink(registry=self, run_id=run_id)

    def _enforce_max_runs(self) -> None:
        if len(self._runs) <= self.config.max_runs:
            return
        candidates = sorted(
            self._runs.values(),
            key=lambda run: (run.status == ExecutionRunStatus.RUNNING, run.updated_at),
        )
        while len(self._runs) > self.config.max_runs and candidates:
            candidate = candidates.pop(0)
            if candidate.status == ExecutionRunStatus.RUNNING:
                continue
            self._runs.pop(candidate.run_id, None)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


def get_run_control_config() -> RunControlConfig:
    settings = get_settings()
    return RunControlConfig(
        max_runs=settings.run_control_max_runs,
        recent_event_buffer_size=settings.run_control_recent_event_buffer_size,
        completed_run_ttl_seconds=settings.run_control_completed_run_ttl_seconds,
        heartbeat_interval_seconds=settings.run_control_heartbeat_interval_seconds,
    )


@lru_cache(maxsize=1)
def get_run_registry() -> RunRegistry:
    """Return the shared in-memory run registry."""

    return RunRegistry(config=get_run_control_config())
