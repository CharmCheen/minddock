"""Active media transcript configuration store backed by a JSON file.

Security:
    The api_key is NEVER written to disk. It lives only in os.environ.
    The file stores api_key_source ("env" | "none") as a marker.

    Rationale: mirrors the LLM Runtime active_config pattern for consistency.
    After a restart, the user must re-enter the API key via the Settings UI
    or set MEDIA_TRANSCRIPT_API_KEY in the shell environment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path("data/active_media_transcript.json")


@dataclass
class ActiveMediaTranscriptConfig:
    """The currently active user-configured media transcript provider."""

    provider: str = "mock"
    base_url: str = ""
    model: str = "whisper-1"
    timeout_seconds: float = 60.0
    enabled: bool = False
    api_key_source: str = "none"  # "env" | "none"
    # Local ASR fields
    local_asr_server_path: str = ""
    local_asr_host: str = ""
    local_asr_port: int = 9001
    local_asr_model: str = "small"
    local_asr_device: str = "auto"
    local_asr_compute_type: str = "int8"
    local_asr_auto_start: bool = True
    local_asr_timeout_seconds: float = 120.0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
            "api_key_source": self.api_key_source,
            "local_asr_server_path": self.local_asr_server_path,
            "local_asr_host": self.local_asr_host,
            "local_asr_port": self.local_asr_port,
            "local_asr_model": self.local_asr_model,
            "local_asr_device": self.local_asr_device,
            "local_asr_compute_type": self.local_asr_compute_type,
            "local_asr_auto_start": self.local_asr_auto_start,
            "local_asr_timeout_seconds": self.local_asr_timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveMediaTranscriptConfig":
        return cls(
            provider=str(data.get("provider", "mock")),
            base_url=str(data.get("base_url", "")),
            model=str(data.get("model", "whisper-1")),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            enabled=bool(data.get("enabled", False)),
            api_key_source=str(data.get("api_key_source", "none")),
            local_asr_server_path=str(data.get("local_asr_server_path", "")),
            local_asr_host=str(data.get("local_asr_host", "")),
            local_asr_port=int(data.get("local_asr_port", 9001)),
            local_asr_model=str(data.get("local_asr_model", "small")),
            local_asr_device=str(data.get("local_asr_device", "auto")),
            local_asr_compute_type=str(data.get("local_asr_compute_type", "int8")),
            local_asr_auto_start=bool(data.get("local_asr_auto_start", True)),
            local_asr_timeout_seconds=float(data.get("local_asr_timeout_seconds", 120.0)),
        )


def get_active_media_transcript_config() -> ActiveMediaTranscriptConfig:
    """Load the active media transcript config from disk, or return a default (disabled) config."""
    if not CONFIG_FILE.exists():
        return ActiveMediaTranscriptConfig()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return ActiveMediaTranscriptConfig.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return ActiveMediaTranscriptConfig()


def save_active_media_transcript_config(
    provider: str,
    base_url: str,
    api_key: str | None,
    model: str,
    timeout_seconds: float,
    enabled: bool,
    *,
    local_asr_server_path: str = "",
    local_asr_host: str = "",
    local_asr_port: int = 9001,
    local_asr_model: str = "small",
    local_asr_device: str = "auto",
    local_asr_compute_type: str = "int8",
    local_asr_auto_start: bool = True,
    local_asr_timeout_seconds: float = 120.0,
) -> ActiveMediaTranscriptConfig:
    """Persist the active media transcript config to disk.

    Security: the api_key is NEVER written to disk.
    It is set in os.environ only. The file only records that a key exists (via api_key_source).
    """
    normalized_api_key = None if api_key is None else api_key.strip()
    current_env_key = os.environ.get("MEDIA_TRANSCRIPT_API_KEY", "").strip()
    should_keep_existing_key = enabled and not normalized_api_key and bool(current_env_key)
    api_key_source = "env" if (enabled and (normalized_api_key or should_keep_existing_key)) else "none"

    config = ActiveMediaTranscriptConfig(
        provider=provider,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
        api_key_source=api_key_source,
        local_asr_server_path=local_asr_server_path,
        local_asr_host=local_asr_host,
        local_asr_port=local_asr_port,
        local_asr_model=local_asr_model,
        local_asr_device=local_asr_device,
        local_asr_compute_type=local_asr_compute_type,
        local_asr_auto_start=local_asr_auto_start,
        local_asr_timeout_seconds=local_asr_timeout_seconds,
    )

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    # Bootstrap env vars so the existing Settings-based system picks them up (in-process only)
    if enabled:
        if normalized_api_key:
            os.environ["MEDIA_TRANSCRIPT_API_KEY"] = normalized_api_key
        elif not should_keep_existing_key:
            os.environ.pop("MEDIA_TRANSCRIPT_API_KEY", None)
        if base_url:
            os.environ["MEDIA_TRANSCRIPT_API_BASE_URL"] = base_url
        else:
            os.environ.pop("MEDIA_TRANSCRIPT_API_BASE_URL", None)
        if model:
            os.environ["MEDIA_TRANSCRIPT_MODEL"] = model
        else:
            os.environ.pop("MEDIA_TRANSCRIPT_MODEL", None)
        os.environ["MEDIA_TRANSCRIPT_TIMEOUT_SECONDS"] = str(timeout_seconds)
        os.environ["MEDIA_TRANSCRIPT_PROVIDER"] = provider
        os.environ["MEDIA_TRANSCRIPT_ENABLED"] = "true"
        # Local ASR env vars
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_SERVER_PATH"] = local_asr_server_path
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_HOST"] = local_asr_host
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_PORT"] = str(local_asr_port)
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_MODEL"] = local_asr_model
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_DEVICE"] = local_asr_device
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_COMPUTE_TYPE"] = local_asr_compute_type
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_AUTO_START"] = "true" if local_asr_auto_start else "false"
        os.environ["MEDIA_TRANSCRIPT_LOCAL_ASR_TIMEOUT_SECONDS"] = str(local_asr_timeout_seconds)
    else:
        os.environ.pop("MEDIA_TRANSCRIPT_API_KEY", None)
        os.environ.pop("MEDIA_TRANSCRIPT_API_BASE_URL", None)
        os.environ.pop("MEDIA_TRANSCRIPT_MODEL", None)
        os.environ.pop("MEDIA_TRANSCRIPT_TIMEOUT_SECONDS", None)
        os.environ.pop("MEDIA_TRANSCRIPT_PROVIDER", None)
        os.environ.pop("MEDIA_TRANSCRIPT_ENABLED", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_SERVER_PATH", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_HOST", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_PORT", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_MODEL", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_DEVICE", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_COMPUTE_TYPE", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_AUTO_START", None)
        os.environ.pop("MEDIA_TRANSCRIPT_LOCAL_ASR_TIMEOUT_SECONDS", None)

    return config


def reset_active_media_transcript_config() -> None:
    """Remove the persisted media transcript config file and clear UI-set env vars.

    Note: we only clear env vars that were set by the UI save flow. If the user
    has MEDIA_TRANSCRIPT_API_KEY in their shell environment, this cannot be
    distinguished from an UI-set key and will also be cleared.
    """
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()

    for key in (
        "MEDIA_TRANSCRIPT_API_KEY",
        "MEDIA_TRANSCRIPT_API_BASE_URL",
        "MEDIA_TRANSCRIPT_MODEL",
        "MEDIA_TRANSCRIPT_TIMEOUT_SECONDS",
        "MEDIA_TRANSCRIPT_PROVIDER",
        "MEDIA_TRANSCRIPT_ENABLED",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_SERVER_PATH",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_HOST",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_PORT",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_MODEL",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_DEVICE",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_COMPUTE_TYPE",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_AUTO_START",
        "MEDIA_TRANSCRIPT_LOCAL_ASR_TIMEOUT_SECONDS",
    ):
        os.environ.pop(key, None)


def get_effective_media_transcript_config_source(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    """Determine where the active media transcript config is coming from.

    Returns one of:
      - "ui_override"  — active config file exists and is enabled
      - "environment"  — no active config file, using env/default
    """
    if active_config.enabled and active_config.provider != "":
        return "ui_override"
    return "environment"


def get_effective_media_transcript_api_key(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    """Resolve the effective API key. UI override > settings/env merged > empty."""
    if active_config.enabled and active_config.api_key_source == "env":
        env_key = os.environ.get("MEDIA_TRANSCRIPT_API_KEY", "").strip()
        if env_key:
            return env_key
    # settings may be monkeypatched or come from .env; env is the raw fallback
    val = str(getattr(settings, "media_transcript_api_key", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_API_KEY", "").strip()


def get_effective_media_transcript_base_url(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    """Resolve the effective base_url. UI override > settings/env merged > empty."""
    if active_config.enabled and active_config.base_url:
        return active_config.base_url
    val = str(getattr(settings, "media_transcript_api_base_url", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_API_BASE_URL", "").strip()


def get_effective_media_transcript_provider(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    """Resolve the effective provider. UI override > settings/env merged > mock."""
    if active_config.enabled and active_config.provider:
        return active_config.provider
    val = str(getattr(settings, "media_transcript_provider", "") or "").strip().lower()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_PROVIDER", "").strip().lower() or "mock"


def get_effective_media_transcript_model(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    """Resolve the effective model. UI override > settings/env merged > whisper-1."""
    if active_config.enabled and active_config.model:
        return active_config.model
    val = str(getattr(settings, "media_transcript_model", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_MODEL", "").strip() or "whisper-1"


def get_effective_media_transcript_timeout(active_config: ActiveMediaTranscriptConfig, settings) -> float:
    """Resolve the effective timeout. UI override > settings/env merged > 60.0."""
    if active_config.enabled:
        return active_config.timeout_seconds
    val = float(getattr(settings, "media_transcript_timeout_seconds", 0) or 0)
    if val > 0:
        return val
    env_val = os.environ.get("MEDIA_TRANSCRIPT_TIMEOUT_SECONDS", "").strip()
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return 60.0


# --- Local ASR effective getters ---

def get_effective_local_asr_server_path(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    if active_config.enabled and active_config.local_asr_server_path:
        return active_config.local_asr_server_path
    val = str(getattr(settings, "media_transcript_local_asr_server_path", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_SERVER_PATH", "").strip()


def get_effective_local_asr_host(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    if active_config.enabled and active_config.local_asr_host:
        return active_config.local_asr_host
    val = str(getattr(settings, "media_transcript_local_asr_host", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_HOST", "").strip() or "127.0.0.1"


def get_effective_local_asr_port(active_config: ActiveMediaTranscriptConfig, settings) -> int:
    if active_config.enabled:
        return active_config.local_asr_port
    val = getattr(settings, "media_transcript_local_asr_port", 0) or 0
    if val:
        return int(val)
    env_val = os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_PORT", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    return 9001


def get_effective_local_asr_model(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    if active_config.enabled and active_config.local_asr_model:
        return active_config.local_asr_model
    val = str(getattr(settings, "media_transcript_local_asr_model", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_MODEL", "").strip() or "small"


def get_effective_local_asr_device(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    if active_config.enabled and active_config.local_asr_device:
        return active_config.local_asr_device
    val = str(getattr(settings, "media_transcript_local_asr_device", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_DEVICE", "").strip() or "auto"


def get_effective_local_asr_compute_type(active_config: ActiveMediaTranscriptConfig, settings) -> str:
    if active_config.enabled and active_config.local_asr_compute_type:
        return active_config.local_asr_compute_type
    val = str(getattr(settings, "media_transcript_local_asr_compute_type", "") or "").strip()
    if val:
        return val
    return os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_COMPUTE_TYPE", "").strip() or "int8"


def get_effective_local_asr_auto_start(active_config: ActiveMediaTranscriptConfig, settings) -> bool:
    if active_config.enabled:
        return active_config.local_asr_auto_start
    val = getattr(settings, "media_transcript_local_asr_auto_start", None)
    if val is not None:
        return bool(val)
    env_val = os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_AUTO_START", "").strip().lower()
    if env_val:
        return env_val in ("true", "1", "yes")
    return True


def get_effective_local_asr_timeout_seconds(active_config: ActiveMediaTranscriptConfig, settings) -> float:
    if active_config.enabled:
        return active_config.local_asr_timeout_seconds
    val = float(getattr(settings, "media_transcript_local_asr_timeout_seconds", 0) or 0)
    if val > 0:
        return val
    env_val = os.environ.get("MEDIA_TRANSCRIPT_LOCAL_ASR_TIMEOUT_SECONDS", "").strip()
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return 120.0
