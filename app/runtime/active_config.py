"""Active runtime configuration store backed by a JSON file.

Phase 1: User-configurable OpenAI-compatible runtime.
Credentials are stored in data/active_runtime.json and bootstrapped
into the environment at startup so the existing registry flow uses them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = Path("data/active_runtime.json")


@dataclass
class ActiveRuntimeConfig:
    """The currently active user-configured runtime."""

    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveRuntimeConfig":
        return cls(
            provider=str(data.get("provider", "openai_compatible")),
            base_url=str(data.get("base_url", "https://api.openai.com/v1")),
            api_key=str(data.get("api_key", "")),
            model=str(data.get("model", "gpt-4o-mini")),
            enabled=bool(data.get("enabled", False)),
        )


def get_active_config() -> ActiveRuntimeConfig:
    """Load the active runtime config from disk, or return a default (disabled) config."""
    if not CONFIG_FILE.exists():
        return ActiveRuntimeConfig()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return ActiveRuntimeConfig.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return ActiveRuntimeConfig()


def save_active_config(config: ActiveRuntimeConfig) -> ActiveRuntimeConfig:
    """Persist the active runtime config to disk."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    return config


def bootstrap_env_from_active_config() -> None:
    """Bootstrap env vars from saved config so existing registry uses them.

    LLM_API_KEY  — picked up by _read_api_key() in the registry.
    LLM_RUNTIME_BASE_URL — picked up by _build_langchain_runtime() as an override.
    """
    config = get_active_config()
    if config.enabled:
        if config.api_key:
            os.environ["LLM_API_KEY"] = config.api_key
        if config.base_url:
            os.environ["LLM_RUNTIME_BASE_URL"] = config.base_url
