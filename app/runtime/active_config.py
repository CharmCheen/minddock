"""Active runtime configuration store backed by local JSON files.

MindDock intentionally maintains one active runtime config. Non-sensitive
settings live in ``data/active_runtime.json``. The API key, when saved through
the UI, lives in ``data/active_runtime_secret.json`` so it can be gitignored
separately from the rest of the configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path("data/active_runtime.json")
SECRET_FILE = Path("data/active_runtime_secret.json")
_API_KEY_PREVIEW_CHARS = 4


@dataclass
class ActiveRuntimeConfig:
    """The currently active user-configured runtime.

    The api_key is not stored in this dataclass or in the non-secret config
    file. ``api_key_source`` is a marker:
    - ``local_secret``: key is stored in SECRET_FILE
    - ``env``: key is expected from LLM_API_KEY
    - ``none``: no key configured
    """

    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key_source: str = "none"
    model: str = "gpt-4o-mini"
    enabled: bool = False
    last_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_source": self.api_key_source,
            "model": self.model,
            "enabled": self.enabled,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveRuntimeConfig":
        return cls(
            provider=str(data.get("provider", "openai_compatible")),
            base_url=str(data.get("base_url", "https://api.openai.com/v1")),
            api_key_source=str(data.get("api_key_source", "none")),
            model=str(data.get("model", "gpt-4o-mini")),
            enabled=bool(data.get("enabled", False)),
            last_error=str(data["last_error"]) if data.get("last_error") else None,
        )


def get_active_config() -> ActiveRuntimeConfig:
    """Load the active runtime config from disk, or return a disabled default.

    When no file exists, provider="" is used as a sentinel so callers can
    distinguish "not configured" from "configured but disabled".
    """

    if not CONFIG_FILE.exists():
        return ActiveRuntimeConfig(provider="")
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return ActiveRuntimeConfig.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return ActiveRuntimeConfig(provider="")


def _write_config(config: ActiveRuntimeConfig) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


def _read_secret_api_key() -> str:
    if not SECRET_FILE.exists():
        return ""
    try:
        with open(SECRET_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ""
    key = data.get("api_key") if isinstance(data, dict) else None
    return str(key or "").strip()


def _write_secret_api_key(api_key: str) -> None:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_key": api_key}, f, indent=2, ensure_ascii=False)


def _delete_secret_api_key() -> None:
    try:
        SECRET_FILE.unlink()
    except FileNotFoundError:
        return


def get_effective_api_key(config: ActiveRuntimeConfig | None = None) -> str:
    """Return the effective key without logging or exposing it in API responses."""

    config = config or get_active_config()
    env_key = os.environ.get("LLM_API_KEY", "").strip()
    if config.api_key_source == "local_secret":
        return _read_secret_api_key() or env_key
    if config.api_key_source == "env":
        return env_key or _read_secret_api_key()
    return env_key if config.provider == "" else ""


def has_configured_api_key(config: ActiveRuntimeConfig | None = None) -> bool:
    return bool(get_effective_api_key(config))


def mask_api_key(config: ActiveRuntimeConfig | None = None) -> str | None:
    key = get_effective_api_key(config)
    if not key:
        return None
    if len(key) <= _API_KEY_PREVIEW_CHARS * 2:
        return "*" * len(key)
    return f"{key[:_API_KEY_PREVIEW_CHARS]}...{key[-_API_KEY_PREVIEW_CHARS:]}"


def save_active_config(
    provider: str,
    base_url: str,
    api_key: str | None,
    model: str,
    enabled: bool,
    clear_api_key: bool = False,
) -> ActiveRuntimeConfig:
    """Persist the active runtime config.

    The non-secret config file never receives the key. A newly supplied key is
    saved to SECRET_FILE. Omitting or blanking api_key preserves the old key;
    only clear_api_key=True deletes it.
    """

    normalized_api_key = None if api_key is None else api_key.strip()
    current_config = get_active_config()
    current_env_key = os.environ.get("LLM_API_KEY", "").strip()
    current_secret_key = _read_secret_api_key()

    selected_key = ""
    api_key_source = "none"
    if enabled and not clear_api_key:
        if normalized_api_key:
            selected_key = normalized_api_key
            api_key_source = "local_secret"
            _write_secret_api_key(normalized_api_key)
        elif current_config.api_key_source == "local_secret" and current_secret_key:
            selected_key = current_secret_key
            api_key_source = "local_secret"
        elif current_config.api_key_source == "env" and current_env_key:
            selected_key = current_env_key
            api_key_source = "env"
        elif current_secret_key:
            selected_key = current_secret_key
            api_key_source = "local_secret"
        elif current_env_key:
            selected_key = current_env_key
            api_key_source = "env"

    if clear_api_key or not enabled:
        _delete_secret_api_key()

    config = ActiveRuntimeConfig(
        provider=provider,
        base_url=base_url,
        api_key_source=api_key_source,
        model=model,
        enabled=enabled,
        last_error=None,
    )
    _write_config(config)

    if enabled:
        if selected_key:
            os.environ["LLM_API_KEY"] = selected_key
        else:
            os.environ.pop("LLM_API_KEY", None)
        if base_url:
            os.environ["LLM_RUNTIME_BASE_URL"] = base_url
        else:
            os.environ.pop("LLM_RUNTIME_BASE_URL", None)
        if model:
            os.environ["LLM_RUNTIME_MODEL"] = model
        else:
            os.environ.pop("LLM_RUNTIME_MODEL", None)
    else:
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("LLM_RUNTIME_BASE_URL", None)
        os.environ.pop("LLM_RUNTIME_MODEL", None)

    return config


def bootstrap_env_from_active_config() -> None:
    """Bootstrap env vars from saved config so existing registry uses them."""

    config = get_active_config()
    if not config.enabled:
        return

    key = get_effective_api_key(config)
    if key:
        os.environ["LLM_API_KEY"] = key
        if config.base_url:
            os.environ["LLM_RUNTIME_BASE_URL"] = config.base_url
        if config.model:
            os.environ["LLM_RUNTIME_MODEL"] = config.model


def record_runtime_error(message: str) -> None:
    """Persist a sanitized last runtime error for the settings UI."""

    config = get_active_config()
    if config.provider == "":
        return
    safe = message.strip()[:240]
    config.last_error = safe or "Runtime invocation failed."
    _write_config(config)


def clear_runtime_error() -> None:
    config = get_active_config()
    if config.provider == "" or not config.last_error:
        return
    config.last_error = None
    _write_config(config)


def get_runtime_status(config: ActiveRuntimeConfig | None = None) -> str:
    config = config or get_active_config()
    if config.provider == "":
        return "not_configured"
    if not config.enabled:
        return "disabled"
    if config.last_error:
        return "unavailable"
    if has_configured_api_key(config):
        return "connected"
    return "unavailable"


def get_effective_runtime_status() -> str:
    """Determine where the currently-active runtime credentials come from."""

    config = get_active_config()

    if config.provider == "":
        if os.environ.get("LLM_API_KEY"):
            return "env_override"
        return "default"

    if config.enabled:
        if config.api_key_source == "local_secret" and _read_secret_api_key():
            return "active_config_secret"
        if config.api_key_source == "env" and os.environ.get("LLM_API_KEY"):
            return "active_config_env"
        return "active_config_disabled"

    if os.environ.get("LLM_API_KEY"):
        return "env_override"

    return "active_config_disabled"
