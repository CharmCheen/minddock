"""Local ASR server with faster-whisper.

Provides an OpenAI-compatible /v1/audio/transcriptions endpoint
and model management endpoints for preload and status checks.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

# Optional faster-whisper import — server starts without it,
# but transcription and preload require it.
try:
    from faster_whisper import WhisperModel

    _HAS_FASTER_WHISPER = True
except Exception:
    _HAS_FASTER_WHISPER = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global model cache and state
# ---------------------------------------------------------------------------

MODEL_CACHE: dict[tuple[str, str, str, str], Any] = {}
MODEL_STATES: dict[tuple[str, str, str, str], dict[str, Any]] = {}
MODEL_LOCKS: dict[tuple[str, str, str, str], threading.Lock] = {}

_STATE_NOT_LOADED = "not_loaded"
_STATE_LOADING = "loading"
_STATE_READY = "ready"
_STATE_FAILED = "failed"


_MODEL_PATH_ENV = {
    "base": "LOCAL_ASR_MODEL_BASE_PATH",
    "small": "LOCAL_ASR_MODEL_SMALL_PATH",
    "medium": "LOCAL_ASR_MODEL_MEDIUM_PATH",
}


def resolve_model_path(model: str) -> tuple[str, str]:
    """Resolve a model name to a local directory override when configured.

    Returns (resolved_model, message). If no override is configured, the
    resolved model remains the original model name. If an override is present
    but invalid, the original model is used and the message explains why.
    """
    normalized = model.strip() or "base"
    env_name = _MODEL_PATH_ENV.get(normalized.lower())
    if env_name is None:
        return normalized, ""

    configured = os.environ.get(env_name, "").strip()
    if not configured:
        return normalized, ""

    path = Path(configured)
    if path.is_dir():
        return str(path), f"Using local model path from {env_name}: {path}"

    return normalized, f"Invalid local model path in {env_name}: {configured}. Falling back to model name '{normalized}'."


def _cache_key(model: str, device: str, compute_type: str) -> tuple[str, str, str, str]:
    resolved_model, _ = resolve_model_path(model)
    return (model, device, compute_type, resolved_model)


def _resolved_model_path(model: str, resolved_model: str) -> str:
    return resolved_model if resolved_model != model and Path(resolved_model).is_dir() else ""


def _get_lock(key: tuple[str, str, str, str]) -> threading.Lock:
    if key not in MODEL_LOCKS:
        MODEL_LOCKS[key] = threading.Lock()
    return MODEL_LOCKS[key]


def _resolve_device(requested_device: str) -> tuple[str, str]:
    """Return (actual_device, compute_type) with auto-fallback logic.

    device=auto:
        Try cuda + int8, then fallback cpu + int8.
    """
    if requested_device == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                return ("cuda", "int8")
        except Exception:
            pass
        return ("cpu", "int8")
    return (requested_device, "int8")


def _do_preload(model: str, device: str, compute_type: str) -> None:
    """Background thread worker that loads the model into cache.

    The loading state is already set by model_preload() before the thread
    starts, so this function only updates the final ready/failed state.
    """
    key = _cache_key(model, device, compute_type)
    lock = _get_lock(key)
    resolved_model, model_path_message = resolve_model_path(model)

    try:
        if not _HAS_FASTER_WHISPER:
            raise RuntimeError("faster-whisper is not installed in this environment.")

        actual_device, actual_compute = _resolve_device(device)
        logger.info("Loading faster-whisper model=%s device=%s compute_type=%s", resolved_model, actual_device, actual_compute)
        wmodel = WhisperModel(resolved_model, device=actual_device, compute_type=actual_compute)

        with lock:
            MODEL_CACHE[key] = wmodel
            MODEL_STATES[key] = {
                "status": _STATE_READY,
                "model": model,
                "resolved_model": resolved_model,
                "model_path": _resolved_model_path(model, resolved_model),
                "requested_device": device,
                "actual_device": actual_device,
                "compute_type": actual_compute,
                "message": "Model is loaded and ready." if not model_path_message else f"Model is loaded and ready. {model_path_message}",
                "timestamp": time.time(),
            }
        logger.info("Model %s loaded successfully on %s.", model, actual_device)

    except Exception as exc:
        logger.exception("Failed to load model %s.", model)
        with lock:
            MODEL_STATES[key] = {
                "status": _STATE_FAILED,
                "model": model,
                "resolved_model": resolved_model,
                "model_path": _resolved_model_path(model, resolved_model),
                "requested_device": device,
                "actual_device": device,
                "compute_type": compute_type,
                "message": f"Model load failed: {exc}" if not model_path_message else f"{model_path_message} Model load failed: {exc}",
                "timestamp": time.time(),
            }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Local ASR server starting. faster-whisper available=%s", _HAS_FASTER_WHISPER)
    yield
    logger.info("Local ASR server shutting down.")


app = FastAPI(title="Local ASR Server", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Model status / preload
# ---------------------------------------------------------------------------

class PreloadRequest(BaseModel):
    model: str
    device: str
    compute_type: str


@app.get("/v1/models/status")
async def model_status(
    model: str = Query(...),
    device: str = Query("auto"),
    compute_type: str = Query("int8"),
) -> dict[str, Any]:
    """Return the current load status of the requested model configuration.

    Does NOT trigger download or load — purely a status read.
    """
    key = _cache_key(model, device, compute_type)
    state = MODEL_STATES.get(key)
    resolved_model, model_path_message = resolve_model_path(model)

    if state is None:
        return {
            "status": _STATE_NOT_LOADED,
            "model": model,
            "resolved_model": resolved_model,
            "model_path": _resolved_model_path(model, resolved_model),
            "requested_device": device,
            "actual_device": "",
            "compute_type": compute_type,
            "message": "Model has not been loaded yet." if not model_path_message else f"Model has not been loaded yet. {model_path_message}",
        }

    return {
        "status": state["status"],
        "model": state["model"],
        "resolved_model": state.get("resolved_model", state["model"]),
        "model_path": state.get("model_path", ""),
        "requested_device": state["requested_device"],
        "actual_device": state.get("actual_device", ""),
        "compute_type": state["compute_type"],
        "message": state["message"],
    }


@app.post("/v1/models/preload")
async def model_preload(body: PreloadRequest) -> dict[str, Any]:
    """Trigger background preload of the requested model.

    - If already ready → return ready immediately.
    - If currently loading → return loading immediately.
    - If not_loaded or failed → start background thread to load.

    Uses per-key locking so repeated preload requests never spawn
    multiple threads for the same model configuration.
    """
    key = _cache_key(body.model, body.device, body.compute_type)
    lock = _get_lock(key)
    resolved_model, model_path_message = resolve_model_path(body.model)

    with lock:
        state = MODEL_STATES.get(key)

        if state is not None and state["status"] == _STATE_READY:
            return {
                "status": _STATE_READY,
                "model": state["model"],
                "resolved_model": state.get("resolved_model", state["model"]),
                "model_path": state.get("model_path", ""),
                "requested_device": state["requested_device"],
                "actual_device": state.get("actual_device", ""),
                "compute_type": state["compute_type"],
                "message": state["message"],
            }

        if state is not None and state["status"] == _STATE_LOADING:
            return {
                "status": _STATE_LOADING,
                "model": state["model"],
                "resolved_model": state.get("resolved_model", state["model"]),
                "model_path": state.get("model_path", ""),
                "requested_device": state["requested_device"],
                "actual_device": state.get("actual_device", ""),
                "compute_type": state["compute_type"],
                "message": state["message"],
            }

        # Synchronously mark loading before starting the thread so
        # concurrent requests see the loading state immediately.
        MODEL_STATES[key] = {
            "status": _STATE_LOADING,
            "model": body.model,
            "resolved_model": resolved_model,
            "model_path": _resolved_model_path(body.model, resolved_model),
            "requested_device": body.device,
            "actual_device": "",
            "compute_type": body.compute_type,
            "message": "Model preload started in background." if not model_path_message else f"Model preload started in background. {model_path_message}",
            "timestamp": time.time(),
        }

    # Start background load (outside the lock to avoid blocking callers)
    thread = threading.Thread(
        target=_do_preload,
        args=(body.model, body.device, body.compute_type),
        daemon=True,
    )
    thread.start()

    return {
        "status": _STATE_LOADING,
        "model": body.model,
        "resolved_model": resolved_model,
        "model_path": _resolved_model_path(body.model, resolved_model),
        "requested_device": body.device,
        "actual_device": "",
        "compute_type": body.compute_type,
        "message": "Model preload started in background." if not model_path_message else f"Model preload started in background. {model_path_message}",
    }


# ---------------------------------------------------------------------------
# OpenAI-compatible transcription endpoint
# ---------------------------------------------------------------------------

@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile,
    model: str = Form("base"),
    response_format: str = Form("json"),
    language: str = Form(""),
) -> dict[str, Any]:
    """Transcribe audio using faster-whisper.

    Requires the model to have been preloaded first.
    """
    if not _HAS_FASTER_WHISPER:
        raise HTTPException(status_code=503, detail="faster-whisper is not available.")

    # Default device/compute for transcription endpoint
    device = "auto"
    compute_type = "int8"
    key = _cache_key(model, device, compute_type)
    state = MODEL_STATES.get(key)
    resolved_model, model_path_message = resolve_model_path(model)

    if state is None or state["status"] != _STATE_READY:
        detail = f"Model '{model}' is not ready. Status: {state['status'] if state else 'not_loaded'}. Please preload first."
        if model_path_message:
            detail = f"{detail} {model_path_message}"
        raise HTTPException(
            status_code=503,
            detail=detail,
        )

    wmodel = MODEL_CACHE.get(key)
    if wmodel is None:
        raise HTTPException(status_code=503, detail="Model cache miss. Please preload.")

    try:
        import tempfile

        suffix = Path(file.filename or "audio.mp3").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        segments, info = wmodel.transcribe(tmp_path, language=language or None)
        text = " ".join(seg.text.strip() for seg in segments)

        Path(tmp_path).unlink(missing_ok=True)

        return {
            "text": text,
            "language": info.language if info else "",
            "duration": info.duration if info else 0.0,
        }
    except Exception as exc:
        logger.exception("Transcription failed.")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=9001)
