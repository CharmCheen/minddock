"""Client-event projection and SSE serialization helpers."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta

from app.api.schemas import ClientEventResponseItem
from app.application.client_events import (
    ClientEvent,
    ClientEventChannel,
    ClientEventKind,
    ClientHeartbeatPayload,
    EventProjector,
    EventVisibility,
    get_event_projector,
)
from app.application.events import ExecutionRun


def project_run_events(
    run: ExecutionRun,
    *,
    debug: bool = False,
    projector: EventProjector | None = None,
) -> tuple[ClientEvent, ...]:
    """Project one execution run into a client-facing event stream."""

    active_projector = projector or get_event_projector()
    return active_projector.project_many(run.events, debug=debug)


def serialize_client_event_sse(event: ClientEvent) -> str:
    """Serialize one client event to SSE wire format."""

    body = ClientEventResponseItem.from_client_event(event).model_dump_json()
    return f"event: {event.kind.value}\ndata: {body}\n\n"


def iter_sse_chunks(events: Iterable[ClientEvent]) -> Iterator[str]:
    """Yield SSE chunks for a client event sequence."""

    for event in events:
        yield serialize_client_event_sse(event)


def inject_heartbeat_events(
    events: tuple[ClientEvent, ...],
    *,
    run_id: str,
    heartbeat_interval_seconds: int,
) -> tuple[ClientEvent, ...]:
    """Insert synthetic heartbeat events when there are long gaps between client events."""

    if heartbeat_interval_seconds <= 0 or not events:
        return events

    output: list[ClientEvent] = []
    next_sequence = 1
    heartbeat_counter = 0
    previous_time: datetime | None = None

    for event in events:
        event_time = _parse_timestamp(event.timestamp)
        if previous_time is not None and event_time > previous_time:
            heartbeat_time = previous_time + timedelta(seconds=heartbeat_interval_seconds)
            while heartbeat_time < event_time:
                heartbeat_counter += 1
                output.append(
                    ClientEvent(
                        event_id=f"hb-{heartbeat_counter}",
                        run_id=run_id,
                        sequence=next_sequence,
                        kind=ClientEventKind.HEARTBEAT,
                        channel=ClientEventChannel.SYSTEM,
                        visibility=EventVisibility.PUBLIC,
                        timestamp=heartbeat_time.isoformat(),
                        payload=ClientHeartbeatPayload(),
                        cursor=f"{run_id}:heartbeat:{heartbeat_counter}",
                    )
                )
                next_sequence += 1
                heartbeat_time += timedelta(seconds=heartbeat_interval_seconds)

        output.append(
            ClientEvent(
                event_id=event.event_id,
                run_id=event.run_id,
                sequence=next_sequence,
                kind=event.kind,
                channel=event.channel,
                visibility=event.visibility,
                timestamp=event.timestamp,
                payload=event.payload,
                cursor=event.cursor,
            )
        )
        next_sequence += 1
        previous_time = event_time

    return tuple(output)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)
