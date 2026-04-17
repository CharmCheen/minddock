"""Integration tests for skill catalog and explicit skill execution routes."""

import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.service_models import ChatServiceResult, UseCaseMetadata


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


def test_skill_catalog_endpoint_lists_safe_skills() -> None:
    from app.api import routes

    client = TestClient(app)
    response = client.get("/frontend/skills")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert "echo" in [item["skill_id"] for item in body["items"]]
    assert "import path" not in json.dumps(body).lower()


def test_skill_detail_endpoint_returns_schema_summary() -> None:
    client = TestClient(app)
    response = client.get("/frontend/skills/echo")

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "echo"
    assert body["input_schema"]["fields"][0]["name"] == "text"
    assert body["output_schema"]["fields"][0]["name"] == "text"


def test_invalid_skill_input_returns_structured_error(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(answer="chat response", citations=[], metadata=UseCaseMetadata(retrieved_count=1))

    monkeypatch.setattr(routes.frontend_facade.chat, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = client.post(
        "/frontend/execute",
        json={
            "task_type": "chat",
            "user_input": "hello",
            "requested_skill_id": "bullet_normalize",
            "requested_skill_arguments": {"text": 123},
            "skill_policy": {"mode": "allowlisted", "allowlist": ["bullet_normalize"]},
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_skill_input"
    assert "bullet_normalize" in body["detail"]


def test_explicit_skill_request_flows_into_final_response_stream_and_run_replay(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)
    routes.frontend_facade.run_registry._runs.clear()

    def fake_run_chat_with_runtime(*, request, runtime, precomputed_hits=None):
        return ChatServiceResult(answer="chat response", citations=[], metadata=UseCaseMetadata(retrieved_count=1))

    monkeypatch.setattr(routes.frontend_facade.chat, "run_chat_with_runtime", fake_run_chat_with_runtime)

    execute_response = client.post(
        "/frontend/execute",
        json={
            "task_type": "chat",
            "user_input": "one\ntwo",
            "requested_skill_id": "bullet_normalize",
            "requested_skill_arguments": {"text": "one\ntwo", "marker": "-"},
            "skill_policy": {"mode": "allowlisted", "allowlist": ["bullet_normalize"]},
            "include_metadata": True,
        },
    )

    assert execute_response.status_code == 200
    execute_body = execute_response.json()
    assert any(artifact["kind"] == "skill_result" for artifact in execute_body["artifacts"])

    stream_response = client.post(
        "/frontend/execute/stream",
        json={
            "task_type": "chat",
            "user_input": "one\ntwo",
            "requested_skill_id": "bullet_normalize",
            "requested_skill_arguments": {"text": "one\ntwo", "marker": "-"},
            "skill_policy": {"mode": "allowlisted", "allowlist": ["bullet_normalize"]},
        },
    )

    assert stream_response.status_code == 200
    events = _parse_sse_body(stream_response.text)
    artifact_events = [event for event in events if event["event"] == "artifact"]
    assert any(event["data"]["payload"]["artifact"]["kind"] == "skill_result" for event in artifact_events)
    run_id = events[0]["data"]["run_id"]

    replay_response = client.get(f"/frontend/runs/{run_id}/events")

    assert replay_response.status_code == 200
    replay_body = replay_response.json()
    assert any(
        item["payload"]["artifact"]["kind"] == "skill_result"
        and item["payload"]["artifact"]["content"]["skill_name"] == "bullet_normalize"
        for item in replay_body["items"]
        if item["kind"] == "artifact"
    )
