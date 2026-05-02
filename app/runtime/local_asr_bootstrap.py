"""Local ASR companion service bootstrap.

Manages the standalone local_asr_server process for MindDock.
Does NOT import faster-whisper into the main process.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

_LOCAL_DEV_KEY = "local-dev-key"
_HEALTH_POLL_INTERVAL = 0.5
_HEALTH_MAX_WAIT = 30.0
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class LocalAsrBootstrapResult:
    status: Literal["skipped", "already_running", "started", "failed"]
    message: str = ""
    base_url: str = ""


def _is_valid_host(host: str) -> bool:
    return host.strip() in _ALLOWED_HOSTS


def _is_valid_port(port: int) -> bool:
    return isinstance(port, int) and 1 <= port <= 65535


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/health"


def _build_start_argv(host: str, port: int) -> list[str]:
    """Return argv list for starting the local ASR server.

    Uses shell=False to prevent command injection.
    """
    return [
        "conda", "run", "-n", "local-asr",
        "uvicorn", "server:app",
        "--host", host,
        "--port", str(port),
    ]


def check_local_asr_health(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if the local ASR server /health responds with 200."""
    try:
        response = httpx.get(_health_url(host, port), timeout=timeout)
        return response.status_code == 200 and response.json().get("status") == "ok"
    except Exception:
        return False


def ensure_local_asr_if_enabled(
    provider: str,
    server_path: str,
    host: str,
    port: int,
    auto_start: bool,
    timeout_seconds: float = 120.0,
) -> LocalAsrBootstrapResult:
    """Ensure the local ASR companion service is running when provider == 'local'.

    Returns:
        skipped          — provider is not 'local' or auto_start is False
        already_running  — /health is already responding
        started          — subprocess started and /health became ready
        failed           — subprocess failed to start or health never became ready
    """
    if provider != "local":
        return LocalAsrBootstrapResult(
            status="skipped",
            message="Provider is not 'local'.",
        )

    if not _is_valid_host(host):
        return LocalAsrBootstrapResult(
            status="failed",
            message=f"Invalid local ASR host: {host}. Allowed: {sorted(_ALLOWED_HOSTS)}",
        )

    if not _is_valid_port(port):
        return LocalAsrBootstrapResult(
            status="failed",
            message=f"Invalid local ASR port: {port}. Must be 1–65535.",
        )

    base_url = f"http://{host}:{port}/v1"

    if check_local_asr_health(host, port, timeout=2.0):
        return LocalAsrBootstrapResult(
            status="already_running",
            message=f"Local ASR server already running at {host}:{port}.",
            base_url=base_url,
        )

    if not auto_start:
        return LocalAsrBootstrapResult(
            status="skipped",
            message=f"Local ASR not running and auto_start is false ({host}:{port}).",
            base_url=base_url,
        )

    server_dir = Path(server_path) if server_path else None
    if server_dir is None or not server_dir.is_dir():
        return LocalAsrBootstrapResult(
            status="failed",
            message=f"Local ASR server path does not exist: {server_path}",
            base_url=base_url,
        )

    argv = _build_start_argv(host, port)

    logger.info("Starting local ASR server: %s in %s", argv, server_dir)
    try:
        subprocess.Popen(
            argv,
            cwd=str(server_dir),
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        logger.exception("Failed to start local ASR server subprocess.")
        return LocalAsrBootstrapResult(
            status="failed",
            message=f"Failed to start local ASR server: {exc}",
            base_url=base_url,
        )

    # Poll /health until ready or timeout
    deadline = time.monotonic() + min(timeout_seconds, _HEALTH_MAX_WAIT)
    while time.monotonic() < deadline:
        time.sleep(_HEALTH_POLL_INTERVAL)
        if check_local_asr_health(host, port, timeout=1.0):
            logger.info("Local ASR server ready at %s:%s.", host, port)
            return LocalAsrBootstrapResult(
                status="started",
                message=f"Local ASR server started and ready at {host}:{port}.",
                base_url=base_url,
            )

    logger.warning("Local ASR server did not become ready within %.1fs.", min(timeout_seconds, _HEALTH_MAX_WAIT))
    return LocalAsrBootstrapResult(
        status="failed",
        message=f"Local ASR server started but health check timed out ({host}:{port}).",
        base_url=base_url,
    )
