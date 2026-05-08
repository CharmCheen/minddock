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
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.retrieval_models import RetrievedChunk
from app.runtime.active_config import ActiveRuntimeConfig


@pytest.fixture
def client(temp_config_file, monkeypatch):
    """Set up isolated config path and clean env for each test."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_RUNTIME_MODEL", raising=False)
    return TestClient(app)


@pytest.fixture
def temp_config_file(monkeypatch, tmp_path):
    """Redirect the config file to a temp path for isolated testing."""
    config_path = tmp_path / "active_runtime.json"
    secret_path = tmp_path / "active_runtime_secret.json"
    monkeypatch.setattr("app.runtime.active_config.CONFIG_FILE", config_path)
    monkeypatch.setattr("app.runtime.active_config.SECRET_FILE", secret_path)
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
        assert "api_key_configured" in data
        assert "enabled" in data
        assert "config_source" in data
        assert "runtime_status" in data
        assert "last_error" in data
        assert "effective_runtime" in data

    def test_effective_runtime_reflects_resolver_profile_not_saved_config(self, client, temp_config_file, monkeypatch):
        from app.api import routes

        config = ActiveRuntimeConfig(
            provider="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key_source="none",
            model="gpt-4o",
            enabled=True,
        )
        temp_config_file.write_text(json.dumps(config.to_dict()))
        monkeypatch.setenv("LLM_API_KEY", "sk-minimax-test")

        runtime_match = SimpleNamespace(
            binding=SimpleNamespace(
                selected_profile_id="default_cloud",
                provider_kind="openai_compatible",
                model_name="MiniMax-M2.7",
                selection_reason="auto:policy_score",
            ),
            profile=SimpleNamespace(
                base_url="https://api.minimaxi.com/v1",
                api_key_env="LLM_API_KEY",
            ),
        )
        original_resolver = routes.frontend_facade.runtime_resolver
        routes.frontend_facade.runtime_resolver = SimpleNamespace(resolve=lambda request: runtime_match)
        try:
            response = client.get("/frontend/runtime-config")
        finally:
            routes.frontend_facade.runtime_resolver = original_resolver

        data = response.json()
        assert data["base_url"] == "https://api.openai.com/v1"
        assert data["model"] == "gpt-4o"
        assert data["config_source"] == "active_config_disabled"
        assert data["effective_runtime"] == {
            "profile_id": "default_cloud",
            "provider_kind": "openai_compatible",
            "model_name": "MiniMax-M2.7",
            "base_url": "https://api.minimaxi.com/v1",
            "source": "auto:policy_score",
            "api_key_masked": True,
        }

    def test_api_key_is_never_returned_as_plaintext(self, client, temp_config_file):
        """Security: api_key must not appear in response JSON."""
        response = client.get("/frontend/runtime-config")
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "sk-test-key" not in body

    def test_disabled_by_default(self, client, temp_config_file):
        response = client.get("/frontend/runtime-config")
        assert response.json()["enabled"] is False

    def test_enabled_config_without_available_key_is_unavailable(self, client, temp_config_file):
        """A saved key marker without an available key must not look usable."""
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
        assert response.json()["api_key_masked"] is False
        assert response.json()["api_key_configured"] is False
        assert response.json()["runtime_status"] == "unavailable"

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
        assert data["api_key_configured"] is True
        assert data["base_url"] == "https://api.example.com/v1"
        assert data["model"] == "gpt-4o"
        assert data["runtime_status"] == "connected"

    def test_save_refreshes_effective_runtime_from_active_env_overrides(self, client, temp_config_file):
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://runtime.example.com/v1",
                "api_key": "sk-test-key-123",
                "model": "demo-model",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["effective_runtime"]["base_url"] == "https://runtime.example.com/v1"
        assert data["effective_runtime"]["model_name"] == "demo-model"
        assert data["effective_runtime"]["api_key_masked"] is True

        refreshed = client.get("/frontend/runtime-config").json()
        assert refreshed["effective_runtime"]["base_url"] == "https://runtime.example.com/v1"
        assert refreshed["effective_runtime"]["model_name"] == "demo-model"
        assert refreshed["effective_runtime"]["api_key_masked"] is True

    def test_api_key_never_persisted_to_disk(self, client, temp_config_file):
        """Security invariant: api_key is never written to the non-secret config file."""
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
        # But api_key_source must be recorded as a gitignored local secret marker
        assert stored["api_key_source"] == "local_secret"
        assert stored["enabled"] is True

    def test_saved_config_records_api_key_source(self, client, temp_config_file):
        """The config file stores api_key_source as a marker, not the actual key."""
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
        assert stored["api_key_source"] == "local_secret"
        assert "sk-persist" not in stored

    def test_secret_file_is_used_after_backend_restart(self, client, temp_config_file, monkeypatch, tmp_path):
        """Saving a key persists it in the gitignored secret file and bootstrap restores it."""
        secret_path = tmp_path / "active_runtime_secret.json"
        monkeypatch.setattr("app.runtime.active_config.SECRET_FILE", secret_path)

        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://restart.example.com/v1",
                "api_key": "sk-restart-secret",
                "model": "restart-model",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        assert secret_path.exists()
        assert "sk-restart-secret" in secret_path.read_text()

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_RUNTIME_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_RUNTIME_MODEL", raising=False)

        from app.runtime.active_config import bootstrap_env_from_active_config

        bootstrap_env_from_active_config()

        assert os.environ["LLM_API_KEY"] == "sk-restart-secret"
        assert os.environ["LLM_RUNTIME_BASE_URL"] == "https://restart.example.com/v1"
        assert os.environ["LLM_RUNTIME_MODEL"] == "restart-model"

        refreshed = client.get("/frontend/runtime-config").json()
        assert refreshed["api_key_configured"] is True
        assert refreshed["config_source"] == "active_config_secret"
        assert refreshed["runtime_status"] == "connected"
        assert "sk-restart-secret" not in json.dumps(refreshed)

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
        """When saving with an api_key, env vars LLM_API_KEY, LLM_RUNTIME_BASE_URL, LLM_RUNTIME_MODEL are set."""
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
        assert os.environ.get("LLM_RUNTIME_BASE_URL") == "https://api.example.com/v1"
        assert os.environ.get("LLM_RUNTIME_MODEL") == "gpt-4o"

    def test_save_blank_key_preserves_existing_process_key(self, client, temp_config_file, monkeypatch):
        """Leaving api_key blank keeps the current in-process key when one exists."""
        monkeypatch.setenv("LLM_API_KEY", "sk-existing-key")
        temp_config_file.write_text(
            json.dumps(
                ActiveRuntimeConfig(
                    provider="openai_compatible",
                    base_url="https://old.example.com/v1",
                    api_key_source="env",
                    model="old-model",
                    enabled=True,
                ).to_dict()
            )
        )

        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://new.example.com/v1",
                "api_key": "",
                "model": "new-model",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["api_key_masked"] is True
        assert data["config_source"] == "active_config_env"
        assert data["base_url"] == "https://new.example.com/v1"
        assert data["model"] == "new-model"
        assert os.environ["LLM_API_KEY"] == "sk-existing-key"
        assert os.environ["LLM_RUNTIME_BASE_URL"] == "https://new.example.com/v1"
        assert os.environ["LLM_RUNTIME_MODEL"] == "new-model"
        stored = json.loads(temp_config_file.read_text())
        assert stored["api_key_source"] == "env"
        assert "sk-existing-key" not in json.dumps(stored)

    def test_save_blank_key_preserves_existing_local_secret(self, client, temp_config_file, monkeypatch, tmp_path):
        secret_path = tmp_path / "active_runtime_secret.json"
        monkeypatch.setattr("app.runtime.active_config.SECRET_FILE", secret_path)
        client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://old.example.com/v1",
                "api_key": "sk-local-secret",
                "model": "old-model",
                "enabled": True,
            },
        )
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://new.example.com/v1",
                "api_key": "",
                "model": "new-model",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["api_key_configured"] is True
        assert data["config_source"] == "active_config_secret"
        assert os.environ["LLM_API_KEY"] == "sk-local-secret"
        assert secret_path.read_text().find("sk-local-secret") != -1

    def test_save_omitted_key_preserves_existing_process_key(self, client, temp_config_file, monkeypatch):
        """Omitting api_key has the same keep-existing meaning as a blank field."""
        monkeypatch.setenv("LLM_API_KEY", "sk-existing-key")

        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://new.example.com/v1",
                "model": "new-model",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["api_key_masked"] is True
        assert os.environ["LLM_API_KEY"] == "sk-existing-key"
        stored = json.loads(temp_config_file.read_text())
        assert stored["api_key_source"] == "env"

    def test_save_blank_key_without_existing_key_does_not_fake_configured_state(self, client, temp_config_file):
        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "",
                "model": "gpt-4o",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["api_key_masked"] is False
        assert response.json()["api_key_configured"] is False
        assert response.json()["config_source"] == "active_config_disabled"
        assert response.json()["runtime_status"] == "unavailable"
        assert "LLM_API_KEY" not in os.environ
        stored = json.loads(temp_config_file.read_text())
        assert stored["api_key_source"] == "none"

    def test_clear_api_key_flag_removes_old_key(self, client, temp_config_file, monkeypatch, tmp_path):
        secret_path = tmp_path / "active_runtime_secret.json"
        monkeypatch.setattr("app.runtime.active_config.SECRET_FILE", secret_path)
        client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-clear-me",
                "model": "gpt-4o",
                "enabled": True,
            },
        )
        assert secret_path.exists()

        response = client.put(
            "/frontend/runtime-config",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "",
                "clear_api_key": True,
                "model": "gpt-4o",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["api_key_configured"] is False
        assert data["api_key_masked"] is False
        assert data["runtime_status"] == "unavailable"
        assert not secret_path.exists()
        assert "LLM_API_KEY" not in os.environ

    def test_save_disabled_clears_env(self, client, temp_config_file, monkeypatch):
        """When saving with enabled=False, all env vars are cleared."""
        monkeypatch.setenv("LLM_API_KEY", "sk-pre-existing")
        monkeypatch.setenv("LLM_RUNTIME_BASE_URL", "https://old.example.com/v1")
        monkeypatch.setenv("LLM_RUNTIME_MODEL", "gpt-3.5")
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
        assert "LLM_RUNTIME_BASE_URL" not in os.environ
        assert "LLM_RUNTIME_MODEL" not in os.environ


class TestTestRuntimeConfig:
    """Tests for POST /frontend/runtime-config/test."""

    def test_empty_api_key_returns_missing_key_without_network_call(self, client, temp_config_file, monkeypatch):
        def fail_if_called(*args, **kwargs):
            raise AssertionError("ChatOpenAI should not be created when api_key is empty")

        monkeypatch.setattr("langchain_openai.ChatOpenAI", fail_if_called)

        response = client.post(
            "/frontend/runtime-config/test",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "   ",
                "model": "gpt-4o-mini",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_kind"] == "missing_api_key"
        assert data["message"] == "API key is required to test this runtime. Enter a key or set LLM_API_KEY in the backend environment."

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

    def test_reset_clears_runtime_model_env(self, client, temp_config_file, monkeypatch):
        """Reset must clear LLM_RUNTIME_MODEL from the environment."""
        monkeypatch.setenv("LLM_RUNTIME_MODEL", "gpt-4o")
        response = client.post("/frontend/runtime-config/reset")
        assert response.status_code == 200
        assert "LLM_RUNTIME_MODEL" not in os.environ


class TestRuntimeModelOverride:
    """Tests verifying LLM_RUNTIME_MODEL env var is used at runtime."""

    def test_registry_uses_runtime_model_env_var(self, monkeypatch, tmp_path):
        """When LLM_RUNTIME_MODEL is set, the runtime must use it instead of profile.model_name."""
        from unittest.mock import patch, MagicMock

        # Isolate config file to temp path
        config_path = tmp_path / "active_runtime.json"
        monkeypatch.setattr("app.runtime.active_config.CONFIG_FILE", config_path)

        # Clear the registry cache so we get a fresh runtime with current env
        from app.runtime.registry import get_runtime_registry
        from app.runtime.profiles import get_runtime_profile_registry
        get_runtime_registry.cache_clear()
        get_runtime_profile_registry.cache_clear()

        from app.runtime.registry import RuntimeProfile

        profile = RuntimeProfile(
            profile_id="test_profile",
            display_name="Test",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="profile-default-model",
            base_url="https://profile.example.com/v1",
            api_key_env="LLM_API_KEY",
            default_generation_params={"temperature": 0},
            tags=("test",),
            enabled=True,
            priority=100,
        )

        # Set the override env vars
        monkeypatch.setenv("LLM_RUNTIME_MODEL", "custom-model-from-env")
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key-for-llm")

        mock_llm_instance = MagicMock()
        mock_model_passed = []

        def capture_model(api_key=None, base_url=None, model=None, timeout=None, temperature=None):
            mock_model_passed.append(model)
            return mock_llm_instance

        with patch("langchain_openai.ChatOpenAI", side_effect=capture_model) as mock_chat_openai:
            reg = get_runtime_registry()
            runtime = reg.create("langchain", profile)

        assert mock_model_passed[0] == "custom-model-from-env", (
            f"Expected model 'custom-model-from-env' but got '{mock_model_passed[0]}'. "
            "LLM_RUNTIME_MODEL env var override is not being applied."
        )

        # Cleanup
        get_runtime_registry.cache_clear()
        get_runtime_profile_registry.cache_clear()

    def test_registry_falls_back_to_profile_model_when_no_env_override(self, monkeypatch, tmp_path):
        """When LLM_RUNTIME_MODEL is NOT set, profile.model_name is used."""
        from unittest.mock import patch, MagicMock

        from app.runtime.registry import get_runtime_registry
        from app.runtime.profiles import get_runtime_profile_registry
        get_runtime_registry.cache_clear()
        get_runtime_profile_registry.cache_clear()

        from app.runtime.registry import RuntimeProfile

        profile = RuntimeProfile(
            profile_id="test_profile2",
            display_name="Test2",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="profile-native-model",
            base_url="https://profile.example.com/v1",
            api_key_env="LLM_API_KEY",
            default_generation_params={"temperature": 0},
            tags=("test",),
            enabled=True,
            priority=100,
        )

        # Ensure no env override
        monkeypatch.delenv("LLM_RUNTIME_MODEL", raising=False)
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")

        mock_llm_instance = MagicMock()
        mock_model_passed = []

        def capture_model(api_key=None, base_url=None, model=None, timeout=None, temperature=None):
            mock_model_passed.append(model)
            return mock_llm_instance

        with patch("langchain_openai.ChatOpenAI", side_effect=capture_model) as mock_chat_openai:
            reg = get_runtime_registry()
            runtime = reg.create("langchain", profile)

        assert mock_model_passed[0] == "profile-native-model"

        # Cleanup
        get_runtime_registry.cache_clear()
        get_runtime_profile_registry.cache_clear()
        monkeypatch.delenv("LLM_API_KEY", raising=False)


class _FakeSearchService:
    def retrieve(self, *, query: str, top_k: int, filters=None):
        return [
            RetrievedChunk(
                text="MindDock stores chunks in local Chroma.",
                doc_id="runtime-doc",
                chunk_id="runtime-chunk",
                source="kb/runtime.md",
                source_type="file",
                title="runtime",
                section="Storage",
                location="Storage",
                ref="runtime > Storage",
                page=None,
                anchor=None,
                distance=0.01,
            )
        ]


class _FakeOpenAIServer:
    def __init__(self, *, content: str = "FAKE_RUNTIME_CALLED_12345", status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code
        self.requests: list[dict[str, object]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", "0") or "0")
                raw_body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw_body or "{}")
                owner.requests.append({"path": self.path, "payload": payload})
                self.send_response(owner.status_code)
                self.send_header("content-type", "application/json")
                self.end_headers()
                if owner.status_code >= 400:
                    self.wfile.write(b'{"error":{"message":"fake runtime failure"}}')
                    return
                body = {
                    "id": "chatcmpl-fake",
                    "object": "chat.completion",
                    "created": 0,
                    "model": payload.get("model", "fake-model"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": owner.content},
                            "finish_reason": "stop",
                        }
                    ],
                }
                self.wfile.write(json.dumps(body).encode("utf-8"))

            def log_message(self, format, *args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _install_fake_search(monkeypatch):
    from app.api import routes
    from app.application.orchestrators import ChatOrchestrator

    monkeypatch.setattr(routes.frontend_facade, "chat", ChatOrchestrator(search_service=_FakeSearchService()))


class TestRuntimeExecutionTrust:
    def test_frontend_execute_calls_fake_runtime_and_reports_effective_model(self, client, monkeypatch):
        unique = "FAKE_RUNTIME_CALLED_12345"
        with _FakeOpenAIServer(content=unique) as fake_server:
            response = client.put(
                "/frontend/runtime-config",
                json={
                    "provider": "openai_compatible",
                    "base_url": fake_server.base_url,
                    "api_key": "sk-runtime-test",
                    "model": "fake-runtime-model-123",
                    "enabled": True,
                },
            )
            assert response.status_code == 200
            _install_fake_search(monkeypatch)

            execute_response = client.post(
                "/frontend/execute",
                json={
                    "task_type": "chat",
                    "user_input": "How does MindDock store chunks in local Chroma?",
                    "include_metadata": True,
                },
            )

        assert execute_response.status_code == 200
        body = execute_response.json()
        assert fake_server.requests
        sent_payload = fake_server.requests[0]["payload"]
        assert sent_payload["model"] == "fake-runtime-model-123"
        assert unique in json.dumps(body)
        assert body["metadata"]["fallback_used"] is False
        assert body["metadata"]["mock_used"] is False
        assert body["metadata"]["runtime_status"] == "real"
        assert body["metadata"]["selected_model_name"] == "fake-runtime-model-123"
        assert body["execution_summary"]["selected_model_name"] == "fake-runtime-model-123"
        assert body["execution_summary"]["fallback_used"] is False

    def test_bad_base_url_fails_closed_without_mock_answer(self, client, monkeypatch):
        with _FakeOpenAIServer(status_code=404) as fake_server:
            response = client.put(
                "/frontend/runtime-config",
                json={
                    "provider": "openai_compatible",
                    "base_url": fake_server.base_url + "/bad",
                    "api_key": "sk-runtime-test",
                    "model": "bad-runtime-model",
                    "enabled": True,
                },
            )
            assert response.status_code == 200
            _install_fake_search(monkeypatch)

            execute_response = client.post(
                "/frontend/execute",
                json={
                    "task_type": "chat",
                    "user_input": "How does MindDock store chunks in local Chroma?",
                    "include_metadata": True,
                },
            )

        assert execute_response.status_code == 502
        body = execute_response.json()
        assert body["error"] == "runtime_invocation_failed"
        assert "Configured LLM runtime failed" in body["detail"]
        assert "MockLLM" not in json.dumps(body)
        assert body["metadata"]["runtime_status"] == "failed"
        assert body["metadata"]["fallback_used"] is False
        assert body["metadata"]["mock_used"] is False
        assert body["metadata"]["selected_model_name"] == "bad-runtime-model"

    def test_no_config_uses_explicit_mock_mode_metadata(self, client, monkeypatch):
        from app.api import routes

        client.post("/frontend/runtime-config/reset")
        routes._clear_runtime_caches()
        _install_fake_search(monkeypatch)

        response = client.post(
            "/frontend/execute",
            json={
                "task_type": "chat",
                "user_input": "How does MindDock store chunks in local Chroma?",
                "include_metadata": True,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["metadata"]["runtime_status"] == "mock"
        assert body["metadata"]["mock_used"] is True
        assert body["metadata"]["fallback_used"] is True
        assert body["metadata"]["runtime_warning"] == "Using mock runtime because no API key is configured."
        assert body["execution_summary"]["runtime_status"] == "mock"
        assert body["artifacts"][0]["metadata"]["runtime_status"] == "mock"
        assert body["artifacts"][0]["metadata"]["runtime_warning"] == "Using mock runtime because no API key is configured."
