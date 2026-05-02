"""Unit tests for local ASR bootstrap.

Rules:
- Do NOT start a real local_asr_server subprocess.
- Mock health check and subprocess.
- No real ASR calls.
- No external network access.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.runtime.local_asr_bootstrap import (
    check_local_asr_health,
    ensure_local_asr_if_enabled,
)


class FakeHttpxGet:
    """Factory for mock httpx.get responses."""

    def __init__(self, ok: bool = True):
        self._ok = ok

    def __call__(self, url: str, *, timeout: float):
        response = MagicMock()
        response.status_code = 200 if self._ok else 503
        response.json.return_value = {"status": "ok" if self._ok else "down"}
        return response


def _monkeypatch_httpx_get(monkeypatch, ok: bool = True):
    import httpx

    monkeypatch.setattr(httpx, "get", FakeHttpxGet(ok=ok))


class TestCheckLocalAsrHealth:
    def test_returns_true_when_health_ok(self, monkeypatch):
        _monkeypatch_httpx_get(monkeypatch, ok=True)
        assert check_local_asr_health("127.0.0.1", 9001) is True

    def test_returns_false_when_health_down(self, monkeypatch):
        _monkeypatch_httpx_get(monkeypatch, ok=False)
        assert check_local_asr_health("127.0.0.1", 9001) is False

    def test_returns_false_on_exception(self, monkeypatch):
        import httpx

        def _raise(*args, **kwargs):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "get", _raise)
        assert check_local_asr_health("127.0.0.1", 9001) is False


class TestEnsureLocalAsrIfEnabled:
    def test_skipped_when_provider_not_local(self, monkeypatch):
        result = ensure_local_asr_if_enabled(
            provider="api",
            server_path="/some/path",
            host="127.0.0.1",
            port=9001,
            auto_start=True,
        )
        assert result.status == "skipped"
        assert "not 'local'" in result.message

    def test_already_running_when_health_ok(self, monkeypatch):
        _monkeypatch_httpx_get(monkeypatch, ok=True)
        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path="/some/path",
            host="127.0.0.1",
            port=9001,
            auto_start=True,
        )
        assert result.status == "already_running"
        assert result.base_url == "http://127.0.0.1:9001/v1"

    def test_skipped_when_health_down_and_auto_start_false(self, monkeypatch):
        _monkeypatch_httpx_get(monkeypatch, ok=False)
        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path="/some/path",
            host="127.0.0.1",
            port=9001,
            auto_start=False,
        )
        assert result.status == "skipped"
        assert "auto_start is false" in result.message

    def test_failed_when_server_path_missing(self, monkeypatch):
        _monkeypatch_httpx_get(monkeypatch, ok=False)
        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path="/does/not/exist",
            host="127.0.0.1",
            port=9001,
            auto_start=True,
        )
        assert result.status == "failed"
        assert "does not exist" in result.message

    def test_started_when_health_becomes_ready(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "local_asr_server"
        server_dir.mkdir()

        # First call returns down, second returns ok
        call_count = [0]

        def _toggle(*args, **kwargs):
            call_count[0] += 1
            response = MagicMock()
            response.status_code = 200 if call_count[0] > 1 else 503
            response.json.return_value = {"status": "ok" if call_count[0] > 1 else "down"}
            return response

        import httpx

        monkeypatch.setattr(httpx, "get", _toggle)

        # Speed up polling
        monkeypatch.setattr("app.runtime.local_asr_bootstrap._HEALTH_POLL_INTERVAL", 0.01)
        monkeypatch.setattr("app.runtime.local_asr_bootstrap._HEALTH_MAX_WAIT", 1.0)

        # Mock subprocess.Popen so we don't really spawn anything
        popen_calls = []

        def _fake_popen(cmd, cwd, shell, stdout, stderr):
            popen_calls.append((cmd, shell))
            return MagicMock()

        monkeypatch.setattr("subprocess.Popen", _fake_popen)

        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path=str(server_dir),
            host="127.0.0.1",
            port=9001,
            auto_start=True,
        )
        assert result.status == "started"
        assert "ready" in result.message
        assert len(popen_calls) == 1
        # argv list, not shell string
        assert isinstance(popen_calls[0][0], list)
        assert popen_calls[0][0][0] == "conda"
        assert "--host" in popen_calls[0][0]
        assert "9001" in popen_calls[0][0]
        # shell=False
        assert popen_calls[0][1] is False

    def test_failed_when_health_never_ready(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "local_asr_server"
        server_dir.mkdir()

        import httpx

        monkeypatch.setattr(httpx, "get", FakeHttpxGet(ok=False))
        monkeypatch.setattr("app.runtime.local_asr_bootstrap._HEALTH_POLL_INTERVAL", 0.01)
        monkeypatch.setattr("app.runtime.local_asr_bootstrap._HEALTH_MAX_WAIT", 0.05)

        monkeypatch.setattr("subprocess.Popen", lambda *a, **k: MagicMock())

        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path=str(server_dir),
            host="127.0.0.1",
            port=9001,
            auto_start=True,
        )
        assert result.status == "failed"
        assert "timed out" in result.message

    def test_failed_when_subprocess_raises(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "local_asr_server"
        server_dir.mkdir()

        import httpx

        monkeypatch.setattr(httpx, "get", FakeHttpxGet(ok=False))

        def _raise(*a, **k):
            raise OSError("cannot spawn")

        monkeypatch.setattr("subprocess.Popen", _raise)

        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path=str(server_dir),
            host="127.0.0.1",
            port=9001,
            auto_start=True,
        )
        assert result.status == "failed"
        assert "cannot spawn" in result.message

    def test_malicious_host_rejected(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "local_asr_server"
        server_dir.mkdir()

        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path=str(server_dir),
            host="127.0.0.1 & calc",
            port=9001,
            auto_start=True,
        )
        assert result.status == "failed"
        assert "Invalid local ASR host" in result.message

    def test_invalid_port_rejected(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "local_asr_server"
        server_dir.mkdir()

        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path=str(server_dir),
            host="127.0.0.1",
            port=99999,
            auto_start=True,
        )
        assert result.status == "failed"
        assert "Invalid local ASR port" in result.message

    def test_negative_port_rejected(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "local_asr_server"
        server_dir.mkdir()

        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path=str(server_dir),
            host="127.0.0.1",
            port=-1,
            auto_start=True,
        )
        assert result.status == "failed"
        assert "Invalid local ASR port" in result.message

    def test_base_url_always_returned_for_valid_host(self, monkeypatch):
        _monkeypatch_httpx_get(monkeypatch, ok=True)
        result = ensure_local_asr_if_enabled(
            provider="local",
            server_path="/some/path",
            host="localhost",
            port=8080,
            auto_start=False,
        )
        assert result.base_url == "http://localhost:8080/v1"
