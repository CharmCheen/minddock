"""Integration tests for /frontend/media-transcript-config API endpoints.

Security invariants:
- api_key is NEVER written to data/active_media_transcript.json
- The file only stores api_key_source ("env" | "none") as a marker
- The actual key lives only in os.environ
- api_key is never returned in API responses

Covers:
- GET /frontend/media-transcript-config      — response structure, api_key masking, config_source
- PUT /frontend/media-transcript-config      — save and bootstrap flow, security invariants
- POST /frontend/media-transcript-config/test — validation, no persistence
- POST /frontend/media-transcript-config/reset — restore default, clean env
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig


@pytest.fixture
def client(temp_config_file, monkeypatch):
    """Set up isolated config path and clean env for each test."""
    for key in (
        "MEDIA_TRANSCRIPT_API_KEY",
        "MEDIA_TRANSCRIPT_API_BASE_URL",
        "MEDIA_TRANSCRIPT_MODEL",
        "MEDIA_TRANSCRIPT_TIMEOUT_SECONDS",
        "MEDIA_TRANSCRIPT_PROVIDER",
        "MEDIA_TRANSCRIPT_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    return TestClient(app)


@pytest.fixture
def temp_config_file(monkeypatch, tmp_path):
    """Redirect the config file to a temp path for isolated testing."""
    config_path = tmp_path / "active_media_transcript.json"
    monkeypatch.setattr("app.runtime.media_transcript_active_config.CONFIG_FILE", config_path)
    return config_path


class TestGetMediaTranscriptConfig:
    """Tests for GET /frontend/media-transcript-config."""

    def test_returns_valid_structure(self, client, temp_config_file):
        response = client.get("/frontend/media-transcript-config")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "provider" in data
        assert "api_key_configured" in data
        assert "base_url_configured" in data
        assert "model" in data
        assert "timeout_seconds" in data
        assert "capability" in data
        assert "limitations" in data
        assert "config_source" in data

    def test_api_key_is_never_returned_as_plaintext(self, client, temp_config_file, monkeypatch):
        """Security: api_key must not appear in response JSON."""
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-test-secret-key")
        response = client.get("/frontend/media-transcript-config")
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "sk-test-secret" not in body
        assert "sk-test" not in body

    def test_api_key_configured_boolean_only(self, client, temp_config_file, monkeypatch):
        """api_key_configured must be boolean, not the key itself."""
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-some-key")
        response = client.get("/frontend/media-transcript-config")
        data = response.json()
        assert isinstance(data["api_key_configured"], bool)
        assert data["api_key_configured"] is True

    def test_api_key_not_configured_when_empty(self, client, temp_config_file):
        response = client.get("/frontend/media-transcript-config")
        data = response.json()
        assert data["api_key_configured"] is False

    def test_config_source_is_environment_by_default(self, client, temp_config_file):
        response = client.get("/frontend/media-transcript-config")
        assert response.json()["config_source"] == "environment"

    def test_config_source_is_ui_override_when_active_config_enabled(self, client, temp_config_file):
        config = ActiveMediaTranscriptConfig(
            provider="api",
            base_url="https://api.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            enabled=True,
            api_key_source="env",
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))
        response = client.get("/frontend/media-transcript-config")
        assert response.json()["config_source"] == "ui_override"

    def test_capability_and_limitations_present(self, client, temp_config_file):
        data = client.get("/frontend/media-transcript-config").json()
        assert data["capability"] == "transcript_only_asr"
        assert "no_frame_understanding" in data["limitations"]
        assert "no_multimodal_embedding" in data["limitations"]


class TestUpdateMediaTranscriptConfig:
    """Tests for PUT /frontend/media-transcript-config."""

    def test_save_provider_and_base_url(self, client, temp_config_file):
        response = client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "model": "whisper-1",
                "timeout_seconds": 60.0,
                "enabled": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "api"
        assert data["base_url_configured"] is True
        assert data["model"] == "whisper-1"
        assert data["enabled"] is True

    def test_save_api_key_does_not_persist_key_to_disk(self, client, temp_config_file):
        """Security: api_key must never appear in the config file."""
        client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-super-secret-asr-key",
                "model": "whisper-1",
                "timeout_seconds": 60.0,
                "enabled": True,
            },
        )
        stored = json.loads(temp_config_file.read_text())
        assert "sk-super-secret" not in json.dumps(stored)
        assert "api_key" not in stored
        assert stored["api_key_source"] == "env"

    def test_save_api_key_sets_env_var(self, client, temp_config_file):
        client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-env-key-123",
                "model": "whisper-1",
                "timeout_seconds": 60.0,
                "enabled": True,
            },
        )
        assert os.environ.get("MEDIA_TRANSCRIPT_API_KEY") == "sk-env-key-123"

    def test_save_api_key_not_returned_in_response(self, client, temp_config_file):
        """Security: saved api_key never appears in response body."""
        response = client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-response-check",
                "model": "whisper-1",
                "timeout_seconds": 60.0,
                "enabled": True,
            },
        )
        body = json.dumps(response.json())
        assert "sk-response-check" not in body

    def test_save_blank_key_preserves_existing_env_key(self, client, temp_config_file, monkeypatch):
        """Leaving api_key blank keeps the current in-process key."""
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-existing-key")
        config = ActiveMediaTranscriptConfig(
            provider="api",
            base_url="https://old.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            enabled=True,
            api_key_source="env",
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "api",
                "base_url": "https://new.example.com/v1",
                "api_key": "",
                "model": "whisper-1",
                "timeout_seconds": 30.0,
                "enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["api_key_configured"] is True
        assert data["config_source"] == "ui_override"
        assert os.environ["MEDIA_TRANSCRIPT_API_KEY"] == "sk-existing-key"
        stored = json.loads(temp_config_file.read_text())
        assert stored["api_key_source"] == "env"

    def test_save_disabled_clears_env(self, client, temp_config_file, monkeypatch):
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-pre-existing")
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_BASE_URL", "https://old.example.com/v1")
        client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "disabled",
                "base_url": "",
                "api_key": "",
                "model": "whisper-1",
                "timeout_seconds": 60.0,
                "enabled": False,
            },
        )
        assert "MEDIA_TRANSCRIPT_API_KEY" not in os.environ
        assert "MEDIA_TRANSCRIPT_API_BASE_URL" not in os.environ

    def test_save_mock_provider(self, client, temp_config_file):
        response = client.put(
            "/frontend/media-transcript-config",
            json={
                "provider": "mock",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "mock"
        assert data["enabled"] is True


class TestResetMediaTranscriptConfig:
    """Tests for POST /frontend/media-transcript-config/reset."""

    def test_reset_removes_config_file(self, client, temp_config_file):
        config = ActiveMediaTranscriptConfig(
            provider="api",
            base_url="https://custom.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            enabled=True,
            api_key_source="env",
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.post("/frontend/media-transcript-config/reset")
        assert response.status_code == 200
        assert not temp_config_file.exists()

    def test_reset_returns_environment_config_source(self, client, temp_config_file):
        config = ActiveMediaTranscriptConfig(
            provider="api",
            base_url="https://custom.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            enabled=True,
            api_key_source="env",
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.post("/frontend/media-transcript-config/reset")
        assert response.json()["config_source"] == "environment"

    def test_reset_clears_env_vars(self, client, temp_config_file, monkeypatch):
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-to-clear")
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_BASE_URL", "https://to-clear.example.com")

        client.post("/frontend/media-transcript-config/reset")
        assert "MEDIA_TRANSCRIPT_API_KEY" not in os.environ
        assert "MEDIA_TRANSCRIPT_API_BASE_URL" not in os.environ

    def test_reset_returns_valid_structure(self, client, temp_config_file):
        response = client.post("/frontend/media-transcript-config/reset")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "provider" in data
        assert "api_key_configured" in data
        assert "config_source" in data


class TestTestMediaTranscriptConfig:
    """Tests for POST /frontend/media-transcript-config/test."""

    def test_mock_provider_always_success(self, client, temp_config_file):
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={"provider": "mock"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["error_kind"] is None

    def test_disabled_provider_always_success(self, client, temp_config_file):
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={"provider": "disabled"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_api_provider_missing_key_returns_error(self, client, temp_config_file):
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "model": "whisper-1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] == "missing_api_key"

    def test_api_provider_missing_base_url_returns_error(self, client, temp_config_file, monkeypatch):
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-test")
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={
                "provider": "api",
                "base_url": "",
                "model": "whisper-1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] == "missing_base_url"

    def test_api_provider_missing_model_returns_error(self, client, temp_config_file, monkeypatch):
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-test")
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "model": "",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] == "missing_model"

    def test_api_provider_config_complete_success(self, client, temp_config_file, monkeypatch):
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-test-valid")
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "model": "whisper-1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["error_kind"] is None

    def test_api_provider_key_from_active_config(self, client, temp_config_file, monkeypatch):
        """Test should find key from active config env source."""
        config = ActiveMediaTranscriptConfig(
            provider="api",
            base_url="https://api.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            enabled=True,
            api_key_source="env",
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))
        monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-from-active-config")

        response = client.post(
            "/frontend/media-transcript-config/test",
            json={"provider": "api"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_test_does_not_persist_config(self, client, temp_config_file):
        """Test must not write to the config file."""
        client.post(
            "/frontend/media-transcript-config/test",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "whisper-1",
            },
        )
        assert not temp_config_file.exists()

    def test_test_response_has_no_api_key(self, client, temp_config_file):
        """Security: test response must not contain the api_key."""
        response = client.post(
            "/frontend/media-transcript-config/test",
            json={
                "provider": "api",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-should-not-leak",
                "model": "whisper-1",
            },
        )
        body = json.dumps(response.json())
        assert "sk-should-not-leak" not in body
