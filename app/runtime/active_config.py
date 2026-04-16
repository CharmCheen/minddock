"""Active runtime configuration store backed by a JSON file.

Phase 1-3: User-configurable OpenAI-compatible runtime.

Security (Phase 3):
    The api_key is NEVER written to disk. It lives only in os.environ.
    The file stores api_key_source ("env" | "none") as a marker.

    Rationale: This is "weak persistence + env-first" — appropriate for
    local single-user deployments. It prevents accidental api_key disclosure
    via git history or shared drives, while keeping the UX functional:
    the user enters the key once per session via the Settings UI.

    Known limitation: after a restart, the user must re-enter the API key.
    A proper secret manager (Vault, AWS SM, etc.) is out of scope for Phase 3.

Observability (Phase 3):
    The config_source field tells you exactly where the active runtime
    credentials are coming from:
      - "active_config_env"  — custom runtime enabled, key is in os.environ
      - "active_config_disabled" — custom runtime disabled, using default
      - "default"            — no active config file, using system defaults
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path("data/active_runtime.json")


@dataclass
class ActiveRuntimeConfig:
    """The currently active user-configured runtime.

    Phase 3 change: api_key is NOT stored in this dataclass.
    Only api_key_source is stored in the file. The actual key lives in os.environ.
    """

    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key_source: str = "none"  # "env" = custom key in env, "none" = no custom key
    model: str = "gpt-4o-mini"
    enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_source": self.api_key_source,
            "model": self.model,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveRuntimeConfig":
        return cls(
            provider=str(data.get("provider", "openai_compatible")),
            base_url=str(data.get("base_url", "https://api.openai.com/v1")),
            api_key_source=str(data.get("api_key_source", "none")),
            model=str(data.get("model", "gpt-4o-mini")),
            enabled=bool(data.get("enabled", False)),
        )


def get_active_config() -> ActiveRuntimeConfig:
    """Load the active runtime config from disk, or return a default (disabled) config.

    When no file exists, returns a config with provider="" as a sentinel.
    get_effective_runtime_status() uses this to distinguish 'no config' from 'config disabled'.
    """
    if not CONFIG_FILE.exists():
        return ActiveRuntimeConfig(provider="")
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return ActiveRuntimeConfig.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return ActiveRuntimeConfig(provider="")


def save_active_config(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    enabled: bool,
) -> ActiveRuntimeConfig:
    """Persist the active runtime config to disk.

    Security (Phase 3): the api_key is NEVER written to disk.
    It is set in os.environ only. The file only records that a key exists (via api_key_source).
    """
    api_key_source = "env" if (enabled and api_key) else "none"

    config = ActiveRuntimeConfig(
        provider=provider,
        base_url=base_url,
        api_key_source=api_key_source,
        model=model,
        enabled=enabled,
    )

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    # Bootstrap env vars so the registry uses them immediately (in-process, not persisted)
    if enabled:
        if api_key:
            os.environ["LLM_API_KEY"] = api_key
        else:
            os.environ.pop("LLM_API_KEY", None)
        if base_url:
            os.environ["LLM_RUNTIME_BASE_URL"] = base_url
    else:
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("LLM_RUNTIME_BASE_URL", None)

    return config


def bootstrap_env_from_active_config() -> None:
    """Bootstrap env vars from saved config so existing registry uses them at startup.

    Called once in FastAPI lifespan on startup.

    Security (Phase 3): this only sets base_url from the file.
    The api_key must come from the user's shell environment (LLM_API_KEY env var),
    or the user must re-enter it via the Settings UI after a restart.

    If LLM_API_KEY is already set in the shell environment, it takes precedence.
    """
    config = get_active_config()
    if config.enabled:
        if config.base_url:
            os.environ["LLM_RUNTIME_BASE_URL"] = config.base_url
        # NOTE: api_key is NOT read from the file. It must come from the shell env
        # or be re-entered via the Settings UI after a restart.


def get_effective_runtime_status() -> str:
    """Determine where the currently-active runtime credentials are coming from.

    Returns one of:
      - "active_config_env"        — custom runtime enabled, key is in os.environ
      - "active_config_disabled"   — custom runtime saved but disabled, using default runtime
      - "env_override"            — no active config but LLM_API_KEY is set in env
      - "default"                 — no config file, using system defaults

    provider="" is used as a sentinel value to detect "no config file was loaded".
    """
    config = get_active_config()

    # No config file existed
    if config.provider == "":
        if os.environ.get("LLM_API_KEY"):
            return "env_override"
        return "default"

    if config.enabled:
        if config.api_key_source == "env" and os.environ.get("LLM_API_KEY"):
            return "active_config_env"
        return "active_config_disabled"

    if os.environ.get("LLM_API_KEY"):
        return "env_override"

    return "active_config_disabled"
