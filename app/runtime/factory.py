"""Runtime factory that materializes adapter instances from resolved bindings."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.exceptions import RuntimeResolutionFailedError
from app.runtime.base import GenerationRuntime
from app.runtime.models import ResolvedRuntimeBinding
from app.runtime.profiles import RuntimeProfileRegistry, get_runtime_profile_registry
from app.runtime.registry import RuntimeRegistry, get_runtime_registry


@dataclass
class RuntimeFactory:
    """Create runtime instances from resolved runtime bindings."""

    runtime_registry: RuntimeRegistry
    profile_registry: RuntimeProfileRegistry

    def create(self, binding: ResolvedRuntimeBinding) -> GenerationRuntime:
        profile = self.profile_registry.get(binding.selected_profile_id)
        if profile.adapter_kind != binding.adapter_kind:
            raise RuntimeResolutionFailedError(
                detail=(
                    f"Resolved runtime binding/profile adapter mismatch: binding='{binding.adapter_kind}' "
                    f"profile='{profile.adapter_kind}'."
                )
            )
        runtime = self.runtime_registry.create(profile.adapter_kind, profile)
        runtime.capabilities = binding.resolved_capabilities
        runtime.runtime_name = binding.adapter_kind
        return runtime


@lru_cache(maxsize=1)
def get_runtime_factory() -> RuntimeFactory:
    return RuntimeFactory(
        runtime_registry=get_runtime_registry(),
        profile_registry=get_runtime_profile_registry(),
    )
