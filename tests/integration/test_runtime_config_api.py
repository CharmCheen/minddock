"""Integration tests for /frontend/runtime-config API endpoints.

Phase 3 security invariants:
- api_key is NEVER written to data/active_runtime.json
- The file only stores api_key_source ("env" | "none") as a marker
- The actual key lives only in os.environ

Covers:
- GET /frontend/runtime-config      — response structure, api_key masking, config_source
- PUT /frontend/runtime-config      — save and bootstrap flow, security invariants
- POST /frontend/runtime-config/test — validation, no persistence
- POST /frontend/runtime-config/reset — restore default, clean env
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.active_config import ActiveRuntimeConfig


@pytest.fixture
def client(temp_config_file, monkeypatch):
    """Set up isolated config path and clean env for each test."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_RUNTIME_BASE_URL", raising=False)
    return TestClient(app)


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
        assert "config_source" in data

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
        """When a file has enabled=True and api_key_source=env, the response reflects it."""
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://api.example.com/v1",
            api_key_source="env",
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
            api_key_source="env",
            model="my-model",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.get("/frontend/runtime-config")
        assert response.json()["base_url"] == "https://my-endpoint.example.com/v1"
        assert response.json()["model"] == "my-model"

    def test_config_source_is_default_when_no_file(self, client, temp_config_file):
        """When no config file exists, config_source should be 'default'."""
        response = client.get("/frontend/runtime-config")
        assert response.json()["config_source"] == "default"

    def test_config_source_is_active_config_disabled_when_disabled(self, client, temp_config_file):
        """When config is disabled, config_source reflects that."""
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://api.example.com/v1",
            api_key_source="none",
            model="gpt-4o",
            enabled=False,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.get("/frontend/runtime-config")
        assert response.json()["config_source"] == "active_config_disabled"

    def test_config_source_active_config_env_when_enabled_with_key_in_env(self, client, temp_config_file, monkeypatch):
        """When enabled and env has LLM_API_KEY, config_source is active_config_env."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://api.example.com/v1",
            api_key_source="env",
            model="gpt-4o",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        response = client.get("/frontend/runtime-config")
        assert response.json()["config_source"] == "active_config_env"


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

    def test_api_key_never_persisted_to_disk(self, client, temp_config_file):
        """PHASE 3 SECURITY INVARIANT: api_key is never written to the config file."""
        client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://secure.example.com/v1",
                "api_key": "sk-super-secret-key-12345",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        stored = json.loads(temp_config_file.read_text())
        # The key itself must NEVER appear in the file
        assert "api_key" not in stored or stored.get("api_key") == ""
        assert "sk-super-secret" not in json.dumps(stored)
        # But api_key_source must be recorded
        assert stored["api_key_source"] == "env"
        assert stored["enabled"] is True

    def test_saved_config_records_api_key_source(self, client, temp_config_file):
        """The file stores api_key_source as a marker, not the actual key."""
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
        assert stored["api_key_source"] == "env"
        assert "sk-persist" not in stored

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

    def test_save_with_key_sets_env_var(self, client, temp_config_file):
        """When saving with an api_key, it must be set in os.environ."""
        client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-env-key",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        assert os.environ.get("LLM_API_KEY") == "sk-env-key"

    def test_save_disabled_clears_env(self, client, temp_config_file, monkeypatch):
        """When saving with enabled=False, env vars are cleared."""
        monkeypatch.setenv("LLM_API_KEY", "sk-pre-existing")
        client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "",
                "model": "gpt-4o",
                "enabled": False,
            },
        )
        assert "LLM_API_KEY" not in os.environ


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
        # First write an enabled config directly to the file
        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://custom.example.com/v1",
            api_key_source="env",
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
            api_key_source="env",
            model="gpt-4o",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))

        client.post("/frontend/runtime-config/reset")

        stored = json.loads(temp_config_file.read_text())
        assert stored["enabled"] is False
        assert stored["api_key_source"] == "none"

    def test_reset_returns_correct_structure(self, client, temp_config_file):
        response = client.post("/frontend/runtime-config/reset")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "base_url" in data
        assert "model" in data
        assert "api_key_masked" in data
        assert "enabled" in data
        assert "config_source" in data

    def test_reset_returns_active_config_disabled_source(self, client, temp_config_file):
        """After reset, config_source should be 'active_config_disabled'."""
        response = client.post("/frontend/runtime-config/reset")
        assert response.json()["config_source"] == "active_config_disabled"
