"""Runtime profile registry and settings-backed profile loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import RuntimeProfileInvalidConfigError, RuntimeProfileNotFoundError
from app.runtime.models import RuntimeCapabilities, RuntimeProfile, RuntimeProfileSummary


def _coerce_capabilities(payload: dict[str, object] | None) -> RuntimeCapabilities | None:
    if payload is None:
        return None
    return RuntimeCapabilities(
        supports_chat=bool(payload.get("supports_chat", False)),
        supports_summarize=bool(payload.get("supports_summarize", False)),
        supports_structured_output=bool(payload.get("supports_structured_output", False)),
        supports_tool_or_skill_invocation=bool(payload.get("supports_tool_or_skill_invocation", False)),
        supports_streaming=bool(payload.get("supports_streaming", False)),
        supports_json_mode=bool(payload.get("supports_json_mode", False)),
        max_context=int(payload["max_context"]) if payload.get("max_context") is not None else None,
        provider_family=str(payload["provider_family"]) if payload.get("provider_family") else None,
    )


def _load_profiles_from_settings() -> tuple[RuntimeProfile, ...]:
    settings = get_settings()
    if not settings.runtime_profiles_json.strip():
        return (
            RuntimeProfile(
                profile_id="default_cloud",
                display_name="Default Cloud",
                adapter_kind="langchain",
                provider_kind="openai_compatible",
                model_name=settings.llm_model,
                base_url=settings.llm_base_url,
                api_key_env="LLM_API_KEY",
                default_generation_params={"temperature": 0},
                tags=("cloud", "quality"),
                enabled=True,
                priority=100,
            ),
        )

    try:
        payload = json.loads(settings.runtime_profiles_json)
    except json.JSONDecodeError as exc:
        raise RuntimeProfileInvalidConfigError(detail=f"runtime_profiles_json is not valid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise RuntimeProfileInvalidConfigError(detail="runtime_profiles_json must be a JSON array of runtime profiles.")

    profiles: list[RuntimeProfile] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise RuntimeProfileInvalidConfigError(detail=f"runtime profile #{index} must be a JSON object.")
        try:
            profile = RuntimeProfile(
                profile_id=str(item["profile_id"]),
                display_name=str(item.get("display_name") or item["profile_id"]),
                adapter_kind=str(item["adapter_kind"]),
                provider_kind=str(item["provider_kind"]),
                model_name=str(item["model_name"]),
                base_url=str(item["base_url"]) if item.get("base_url") else None,
                api_key_env=str(item["api_key_env"]) if item.get("api_key_env") else None,
                default_generation_params=dict(item.get("default_generation_params") or {}),
                declared_capabilities=_coerce_capabilities(item.get("declared_capabilities")),
                tags=tuple(str(tag) for tag in item.get("tags", [])),
                enabled=bool(item.get("enabled", True)),
                priority=int(item.get("priority", 100)),
            )
        except KeyError as exc:
            raise RuntimeProfileInvalidConfigError(detail=f"runtime profile #{index} is missing required field '{exc.args[0]}'.") from exc
        profiles.append(profile)
    return tuple(profiles)


@dataclass
class RuntimeProfileRegistry:
    """Registry for runtime profiles independent from adapter registration."""

    profiles: dict[str, RuntimeProfile] = field(default_factory=dict)

    def register(self, profile: RuntimeProfile) -> None:
        self.profiles[profile.profile_id] = profile

    def get(self, profile_id: str) -> RuntimeProfile:
        if profile_id not in self.profiles:
            raise RuntimeProfileNotFoundError(detail=f"Runtime profile '{profile_id}' was not found.")
        return self.profiles[profile_id]

    def list_profiles(self, *, include_disabled: bool = False) -> tuple[RuntimeProfile, ...]:
        items = [
            profile
            for profile in self.profiles.values()
            if include_disabled or profile.enabled
        ]
        return tuple(sorted(items, key=lambda item: (-item.priority, item.profile_id)))

    def list_summaries(self, *, include_disabled: bool = True, capability_overrides: dict[str, RuntimeCapabilities] | None = None) -> tuple[RuntimeProfileSummary, ...]:
        capability_overrides = capability_overrides or {}
        summaries: list[RuntimeProfileSummary] = []
        for profile in self.list_profiles(include_disabled=include_disabled):
            capabilities = capability_overrides.get(profile.profile_id) or profile.declared_capabilities or RuntimeCapabilities()
            summaries.append(
                RuntimeProfileSummary(
                    profile_id=profile.profile_id,
                    display_name=profile.display_name,
                    provider_kind=profile.provider_kind,
                    model_name=profile.model_name,
                    tags=profile.tags,
                    enabled=profile.enabled,
                    capabilities=capabilities.labels(),
                )
            )
        return tuple(summaries)


@lru_cache(maxsize=1)
def get_runtime_profile_registry() -> RuntimeProfileRegistry:
    registry = RuntimeProfileRegistry()
    for profile in _load_profiles_from_settings():
        registry.register(profile)
    return registry
