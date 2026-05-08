"""Integration tests for schedule candidate API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with isolated schedule store."""
    from app.schedule.store import ScheduleCandidateStore
    from app.services.schedule_candidate_service import ScheduleCandidateService
    from fastapi import FastAPI

    # Use a temporary store file
    store_file = tmp_path / "schedule_candidates.json"
    test_store = ScheduleCandidateStore(file_path=store_file)
    test_service = ScheduleCandidateService(store=test_store)

    # Patch the module-level service
    import app.api.schedule_routes as routes_module
    routes_module._service = test_service

    app = FastAPI()
    app.include_router(routes_module.router)

    with TestClient(app) as c:
        yield c


class TestScheduleCandidateAPI:
    def test_list_empty(self, client):
        resp = client.get("/frontend/schedule-candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_with_status_filter(self, client):
        resp = client.get("/frontend/schedule-candidates", params={"status": "pending"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_invalid_status_returns_400(self, client):
        resp = client.get("/frontend/schedule-candidates", params={"status": "bogus"})
        assert resp.status_code == 400

    def test_confirm_not_found_returns_404(self, client):
        resp = client.post("/frontend/schedule-candidates/nonexistent/confirm")
        assert resp.status_code == 404

    def test_dismiss_not_found_returns_404(self, client):
        resp = client.post("/frontend/schedule-candidates/nonexistent/dismiss")
        assert resp.status_code == 404


class TestScheduleSkillAPI:
    def test_skill_run_endpoint_exists(self, client):
        resp = client.post("/frontend/skills/schedule-extraction/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_id"] == "schedule_extraction"
        assert "scan_result" in data
        assert "summary_text" in data
