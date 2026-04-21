"""Compatibility factory helpers for the generation runtime.

The primary runtime path is now exposed through ``app.runtime``.
This module remains as a compatibility bridge so existing service imports and
tests can keep using ``get_generation_runtime()`` while the architecture moves
toward a runtime port/adapter model.
"""

from __future__ import annotations

from functools import lru_cache

from app.runtime import GenerationRuntime, ResolvedRuntimeBinding
from app.core.exceptions import RuntimeResolutionFailedError
from app.runtime.factory import get_runtime_factory
from app.runtime.profiles import get_runtime_profile_registry

LangChainGenerationRuntime = GenerationRuntime


@lru_cache(maxsize=1)
def get_generation_runtime() -> GenerationRuntime:
    """Return the default registered generation runtime."""

    profiles = get_runtime_profile_registry().list_profiles(include_disabled=False)
    if not profiles:
        raise RuntimeResolutionFailedError(detail="No enabled runtime profiles are configured.")
    profile = profiles[0]
    factory = get_runtime_factory()
    return factory.create(
        binding=ResolvedRuntimeBinding(
            selected_profile_id=profile.profile_id,
            adapter_kind=profile.adapter_kind,
            provider_kind=profile.provider_kind,
            model_name=profile.model_name,
            resolved_capabilities=factory.runtime_registry.resolve_capabilities(profile),
            fallback_used=False,
            selection_reason="legacy_default_profile",
        )
    )


def get_llm_provider():
    """Return the provider attached to the default runtime when available."""

    runtime = get_generation_runtime()
    provider = getattr(runtime, "provider", None)
    if provider is None:
        raise RuntimeError("The configured runtime does not expose a direct provider.")
    return provider
