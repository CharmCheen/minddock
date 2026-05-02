"""Regression tests for tools/local_asr_server server.py

Rules:
- Do NOT start a real local_asr_server subprocess.
- Do NOT import or initialize real WhisperModel.
- Do NOT download models.
- Do NOT call /v1/audio/transcriptions.
- Monkeypatch threading.Thread and faster_whisper to keep tests fast and offline.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add tools/local_asr_server to import path
_SERVER_DIR = Path(__file__).resolve().parents[2] / "tools" / "local_asr_server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

# FastAPI UploadFile/Form needs python-multipart at import time.
# Stub it so server.py can be imported without the real package.
_multipart_stub = MagicMock()
_multipart_stub.__version__ = "0.0.20"
if "python_multipart" not in sys.modules:
    sys.modules["python_multipart"] = _multipart_stub

_multipart_pkg = MagicMock()
_multipart_pkg.__version__ = "0.0.20"
_multipart_pkg.multipart = MagicMock()
_multipart_pkg.multipart.parse_options_header = MagicMock()
if "multipart" not in sys.modules:
    sys.modules["multipart"] = _multipart_pkg
if "multipart.multipart" not in sys.modules:
    sys.modules["multipart.multipart"] = _multipart_pkg.multipart


@pytest.fixture(autouse=True)
def _clean_global_state():
    """Reset global caches before every test."""
    import server as _server

    _server.MODEL_CACHE.clear()
    _server.MODEL_STATES.clear()
    _server.MODEL_LOCKS.clear()
    yield
    _server.MODEL_CACHE.clear()
    _server.MODEL_STATES.clear()
    _server.MODEL_LOCKS.clear()


class TestModelPreloadConcurrency:
    """Verify model_preload() guards against duplicate background threads."""

    def test_sets_loading_before_thread_start(self):
        """The loading state must be written before thread.start() is called."""
        import server as _server

        started_threads = []

        def _record_start(self):
            started_threads.append(self)
            # Do NOT call real start to avoid the thread racing to failed

        with patch.object(threading.Thread, "start", _record_start):
            with patch.object(_server, "_HAS_FASTER_WHISPER", False):
                result = asyncio.run(
                    _server.model_preload(
                        MagicMock(model="small", device="auto", compute_type="int8")
                    )
                )

        assert result["status"] == "loading"
        assert len(started_threads) == 1
        key = ("small", "auto", "int8")
        assert _server.MODEL_STATES.get(key, {}).get("status") == "loading"

    def test_duplicate_preload_does_not_spawn_second_thread(self):
        """If already loading, a second preload must not start another thread."""
        import server as _server

        started_threads = []

        def _fake_start(self):
            started_threads.append(self)
            # Do not call real start to avoid spawning a real thread

        with patch.object(threading.Thread, "start", _fake_start):
            with patch.object(_server, "_HAS_FASTER_WHISPER", False):
                # First preload
                r1 = asyncio.run(
                    _server.model_preload(
                        MagicMock(model="small", device="auto", compute_type="int8")
                    )
                )
                # Second preload while still loading
                r2 = asyncio.run(
                    _server.model_preload(
                        MagicMock(model="small", device="auto", compute_type="int8")
                    )
                )

        assert r1["status"] == "loading"
        assert r2["status"] == "loading"
        assert len(started_threads) == 1, "Only one thread should have been started"

    def test_ready_reuse_does_not_start_thread(self):
        """If already ready, preload returns ready and never starts a thread."""
        import server as _server

        key = ("small", "auto", "int8")
        _server.MODEL_STATES[key] = {
            "status": "ready",
            "model": "small",
            "requested_device": "auto",
            "actual_device": "cuda",
            "compute_type": "int8",
            "message": "Ready",
            "timestamp": 0.0,
        }

        started_threads = []

        def _fake_start(self):
            started_threads.append(self)

        with patch.object(threading.Thread, "start", _fake_start):
            result = asyncio.run(
                _server.model_preload(
                    MagicMock(model="small", device="auto", compute_type="int8")
                )
            )

        assert result["status"] == "ready"
        assert result["actual_device"] == "cuda"
        assert len(started_threads) == 0, "No thread should start when already ready"

    def test_failed_allows_re_preload(self):
        """If previously failed, a new preload is allowed to start."""
        import server as _server

        key = ("small", "auto", "int8")
        _server.MODEL_STATES[key] = {
            "status": "failed",
            "model": "small",
            "requested_device": "auto",
            "actual_device": "",
            "compute_type": "int8",
            "message": "Previous failure",
            "timestamp": 0.0,
        }

        started_threads = []

        def _fake_start(self):
            started_threads.append(self)

        with patch.object(threading.Thread, "start", _fake_start):
            with patch.object(_server, "_HAS_FASTER_WHISPER", False):
                result = asyncio.run(
                    _server.model_preload(
                        MagicMock(model="small", device="auto", compute_type="int8")
                    )
                )

        assert result["status"] == "loading"
        assert len(started_threads) == 1, "Re-preload after failed should start one thread"


class TestDoPreload:
    """Verify _do_preload final state transitions."""

    def test_final_state_is_ready_when_whisper_succeeds(self):
        """_do_preload writes ready when WhisperModel initializes."""
        import server as _server

        fake_model = MagicMock()
        _server.WhisperModel = MagicMock(return_value=fake_model)
        _server._HAS_FASTER_WHISPER = True

        _server._do_preload("small", "auto", "int8")

        key = ("small", "auto", "int8")
        assert _server.MODEL_STATES[key]["status"] == "ready"
        assert _server.MODEL_CACHE[key] is fake_model

    def test_final_state_is_failed_when_whisper_missing(self):
        """_do_preload writes failed when faster-whisper is unavailable."""
        import server as _server

        _server._HAS_FASTER_WHISPER = False
        _server._do_preload("small", "auto", "int8")

        key = ("small", "auto", "int8")
        assert _server.MODEL_STATES[key]["status"] == "failed"
        assert "not installed" in _server.MODEL_STATES[key]["message"].lower()

    def test_final_state_is_failed_on_whisper_exception(self):
        """_do_preload writes failed when WhisperModel raises."""
        import server as _server

        _server.WhisperModel = MagicMock(side_effect=RuntimeError("OOM"))
        _server._HAS_FASTER_WHISPER = True

        _server._do_preload("small", "auto", "int8")

        key = ("small", "auto", "int8")
        assert _server.MODEL_STATES[key]["status"] == "failed"
        assert "OOM" in _server.MODEL_STATES[key]["message"]
