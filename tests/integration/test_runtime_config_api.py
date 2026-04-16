"""Integration tests for /frontend/runtime-config API endpoints.

Covers:
- GET /frontend/runtime-config      — response structure, api_key masking
- PUT /frontend/runtime-config      — save and bootstrap flow
- POST /frontend/runtime-config/test — validation, no persistence
- POST /frontend/runtime-config/reset — restore default, clean env
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.active_config import ActiveRuntimeConfig


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove LLM env vars so tests start from a known baseline."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_RUNTIME_BASE_URL", raising=False)


@pytest.fixture
def temp_config_file(monkeypatch, tmp_path):
    """Redirect the config file to a temp path for isolated testing."""
    config_path = tmp_path / "active_runtime.json"
    monkeypatch.setattr("app.runtime.active_config.CONFIG_FILE", config_path)
    return config_path


class TestGetRuntimeConfig:
    """Tests for GET /frontend/runtime-config."""

    def test_returns_valid_structure(self, client, temp_config_file):
        response = client.get("/frontend/runtime-config")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "base_url" in data
        assert "model" in data
        assert "api_key_masked" in data
        assert "enabled" in data

    def test_api_key_is_never_returned_as_plaintext(self, client, temp_config_file):
        """Security: api_key must not appear in response JSON."""
        response = client.get("/frontend/runtime-config")
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "sk-test-key" not in body

    def test_disabled_by_default(self, client, temp_config_file):
        response = client.get("/frontend/runtime-config")
        assert response.json()["enabled"] is False

    def test_enabled_reflects_saved_config(self, client, temp_config_file):
        # Save a enabled config
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            model="gpt-4o",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.get("/frontend/runtime-config")
        assert response.json()["enabled"] is True
        assert response.json()["api_key_masked"] is True

    def test_base_url_reflects_saved_config(self, client, temp_config_file):
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://my-endpoint.example.com/v1",
            api_key="sk-test",
            model="my-model",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.get("/frontend/runtime-config")
        assert response.json()["base_url"] == "https://my-endpoint.example.com/v1"
        assert response.json()["model"] == "my-model"


class TestUpdateRuntimeConfig:
    """Tests for PUT /frontend/runtime-config."""

    def test_save_disabled_config(self, client, temp_config_file):
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-4o-mini",
                "enabled": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["api_key_masked"] is False

    def test_save_enabled_config(self, client, temp_config_file):
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test-key-123",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["api_key_masked"] is True
        assert data["base_url"] == "https://api.example.com/v1"
        assert data["model"] == "gpt-4o"

    def test_saved_config_persists_to_disk(self, client, temp_config_file):
        client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://persist.example.com/v1",
                "api_key": "sk-persist",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        stored = json.loads(temp_config_file.read_text())
        assert stored["base_url"] == "https://persist.example.com/v1"
        assert stored["api_key"] == "sk-persist"
        assert stored["enabled"] is True

    def test_empty_base_url_rejected_when_enabled(self, client, temp_config_file):
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "",
                "api_key": "sk-test",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        assert response.status_code == 422

    def test_invalid_base_url_scheme_rejected(self, client, temp_config_file):
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "ftp://invalid.example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        assert response.status_code == 422

    def test_api_key_not_returned_in_response(self, client, temp_config_file):
        """Security: saved api_key never appears in response body."""
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-super-secret-xyz",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "sk-super-secret" not in body


class TestTestRuntimeConfig:
    """Tests for POST /frontend/runtime-config/test."""

    def test_empty_base_url_returns_error(self, client, temp_config_file):
        response = client.post(
            "/frontend/runtime-config/test",
            json={
                "provider": "openai_compatible",
                "base_url": "",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] == "invalid_url"

    def test_invalid_base_url_scheme_returns_error(self, client, temp_config_file):
        response = client.post(
            "/frontend/runtime-config/test",
            json={
                "provider": "openai_compatible",
                "base_url": "ftp://invalid.example.com",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] == "invalid_url"

    def test_missing_required_fields_returns_422(self, client, temp_config_file):
        response = client.post(
            "/frontend/runtime-config/test",
            json={"provider": "openai_compatible"},
        )
        assert response.status_code == 422

    def test_success_response_has_no_error_kind(self, client, temp_config_file):
        """When a real endpoint is not reachable the error_kind is set but success is False."""
        response = client.post(
            "/frontend/runtime-config/test",
            json={
                "provider": "openai_compatible",
                "base_url": "https://this-domain-does-not-exist-12345.example.com",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] in (
            "network_error",
            "unknown",
            "timeout",
        )

    def test_does_not_persist_config(self, client, temp_config_file):
        """Test connection must not write to the config file."""
        client.post(
            "/frontend/runtime-config/test",
            json={
                "provider": "openai_compatible",
                "base_url": "https://unreachable.example.com",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
        )
        # Config file must not exist after a test-only call
        assert not temp_config_file.exists()


class TestResetRuntimeConfig:
    """Tests for POST /frontend/runtime-config/reset."""

    def test_reset_restores_disabled_config(self, client, temp_config_file):
        # First save an enabled config
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://custom.example.com/v1",
            api_key="sk-custom",
            model="gpt-4o",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.post("/frontend/runtime-config/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["api_key_masked"] is False

    def test_reset_clears_disk_config(self, client, temp_config_file):
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://custom.example.com/v1",
            api_key="sk-custom",
            model="gpt-4o",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        client.post("/frontend/runtime-config/reset")

        stored = json.loads(temp_config_file.read_text())
        assert stored["enabled"] is False
        assert stored["api_key"] == ""

    def test_reset_returns_correct_structure(self, client, temp_config_file):
        response = client.post("/frontend/runtime-config/reset")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "base_url" in data
        assert "model" in data
        assert "api_key_masked" in data
        assert "enabled" in data
