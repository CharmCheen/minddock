"""Capability-aware runtime profile resolution."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import (
    RuntimeProfileCapabilityMismatchError,
    RuntimeProfileDisabledError,
    RuntimeProfileNotFoundError,
    RuntimeResolutionFailedError,
    UnsupportedExecutionModeError,
)
from app.runtime.models import (
    ExecutionPolicy,
    LocalityPreference,
    OptimizationTarget,
    ResolvedRuntimeBinding,
    RuntimeCapabilities,
    RuntimeProfile,
    RuntimeSelectionMode,
    RuntimeSelectionRequest,
    RuntimeSelectionResult,
)
from app.runtime.profiles import RuntimeProfileRegistry, get_runtime_profile_registry
from app.runtime.registry import RuntimeRegistry, get_runtime_registry


@dataclass
class RuntimeResolver:
    """Resolve a runtime binding from execution request + profiles + adapter capabilities."""

    runtime_registry: RuntimeRegistry
    profile_registry: RuntimeProfileRegistry

    def resolve(self, request: RuntimeSelectionRequest) -> RuntimeSelectionResult:
        if request.task_type == "search":
            raise UnsupportedExecutionModeError(detail="Search does not require runtime profile resolution.")

        execution_policy = request.execution_policy
        fallback_used = False
        selection_reason = ""

        if execution_policy.selection_mode in {RuntimeSelectionMode.PREFERRED, RuntimeSelectionMode.STRICT} and execution_policy.preferred_profile_id:
            preferred = self._resolve_preferred_profile(execution_policy.preferred_profile_id)
            if self._matches(preferred, request):
                selection_reason = f"{execution_policy.selection_mode.value}:preferred_profile"
                return self._to_result(preferred, fallback_used=fallback_used, selection_reason=selection_reason)
            if execution_policy.selection_mode == RuntimeSelectionMode.STRICT:
                raise RuntimeProfileCapabilityMismatchError(
                    detail=(
                        f"Runtime profile '{preferred.profile_id}' does not satisfy required capabilities: "
                        f"{', '.join(self._required_capability_names(request)) or 'none'}."
                    )
                )
            fallback_used = True

        candidates = self._candidate_profiles(execution_policy)
        scored = [
            (self._score_profile(profile, request), profile)
            for profile in candidates
            if self._matches(profile, request)
        ]
        if not scored:
            if execution_policy.preferred_profile_id and execution_policy.selection_mode == RuntimeSelectionMode.PREFERRED:
                raise RuntimeProfileCapabilityMismatchError(
                    detail=(
                        f"Preferred runtime profile '{execution_policy.preferred_profile_id}' could not be resolved and no fallback profile matched."
                    )
                )
            raise RuntimeResolutionFailedError(
                detail=f"No enabled runtime profile satisfies required capabilities: {', '.join(self._required_capability_names(request)) or 'none'}."
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        if selection_reason == "":
            selection_reason = f"{execution_policy.selection_mode.value}:policy_score"
        elif fallback_used:
            selection_reason = f"{selection_reason}->fallback:{selected.profile_id}"
        return self._to_result(selected, fallback_used=fallback_used, selection_reason=selection_reason)

    def list_profile_summaries(self) -> tuple:
        capability_map = {
            profile.profile_id: self.runtime_registry.resolve_capabilities(profile)
            for profile in self.profile_registry.list_profiles(include_disabled=True)
            if self.runtime_registry.has_adapter(profile.adapter_kind)
        }
        return self.profile_registry.list_summaries(include_disabled=True, capability_overrides=capability_map)

    def _resolve_preferred_profile(self, profile_id: str) -> RuntimeProfile:
        profile = self.profile_registry.get(profile_id)
        if not profile.enabled:
            raise RuntimeProfileDisabledError(detail=f"Runtime profile '{profile.profile_id}' is disabled.")
        if not self.runtime_registry.has_adapter(profile.adapter_kind):
            raise RuntimeResolutionFailedError(detail=f"Adapter kind '{profile.adapter_kind}' is not registered.")
        return profile

    def _candidate_profiles(self, execution_policy: ExecutionPolicy) -> tuple[RuntimeProfile, ...]:
        profiles = list(self.profile_registry.list_profiles(include_disabled=False))
        if execution_policy.allowed_profile_ids:
            allowed = set(execution_policy.allowed_profile_ids)
            profiles = [profile for profile in profiles if profile.profile_id in allowed]
        filtered = [profile for profile in profiles if self.runtime_registry.has_adapter(profile.adapter_kind)]
        return tuple(filtered)

    def _matches(self, profile: RuntimeProfile, request: RuntimeSelectionRequest) -> bool:
        capabilities = self.runtime_registry.resolve_capabilities(profile)
        if request.task_type == "chat" and not capabilities.supports_chat:
            return False
        if request.task_type == "summarize" and not capabilities.supports_summarize:
            return False
        if request.task_type == "structured_generation" and not capabilities.supports_structured_output:
            return False
        if request.policy.require_structured_output and not capabilities.supports_structured_output:
            return False
        if request.execution_policy.require_structured_output and not capabilities.supports_structured_output:
            return False
        if request.execution_policy.require_skill_support and not capabilities.supports_tool_or_skill_invocation:
            return False
        locality = request.execution_policy.locality_preference
        tags = set(profile.tags)
        if locality == LocalityPreference.LOCAL_ONLY and "local" not in tags:
            return False
        return True

    def _required_capability_names(self, request: RuntimeSelectionRequest) -> tuple[str, ...]:
        required: list[str] = []
        if request.task_type == "chat":
            required.append("supports_chat")
        elif request.task_type == "summarize":
            required.append("supports_summarize")
        elif request.task_type == "structured_generation":
            required.append("supports_structured_output")
        if request.policy.require_structured_output or request.execution_policy.require_structured_output:
            required.append("supports_structured_output")
        if request.execution_policy.require_skill_support:
            required.append("supports_tool_or_skill_invocation")
        return tuple(dict.fromkeys(required))

    def _score_profile(self, profile: RuntimeProfile, request: RuntimeSelectionRequest) -> tuple[int, int, str]:
        score = profile.priority
        tags = set(profile.tags)
        target = request.execution_policy.optimization_target
        locality = request.execution_policy.locality_preference
        if target == OptimizationTarget.LATENCY and "fast" in tags:
            score += 50
        if target == OptimizationTarget.QUALITY and "quality" in tags:
            score += 50
        if target == OptimizationTarget.COST and "cheap" in tags:
            score += 50
        if target == OptimizationTarget.PRIVACY and "private" in tags:
            score += 50
        if locality == LocalityPreference.CLOUD_PREFERRED and "cloud" in tags:
            score += 25
        if locality == LocalityPreference.CLOUD_ALLOWED and "local" in tags:
            score += 5
        if request.execution_policy.preferred_profile_id == profile.profile_id:
            score += 100
        return (score, profile.priority, profile.profile_id)

    def _to_result(self, profile: RuntimeProfile, *, fallback_used: bool, selection_reason: str) -> RuntimeSelectionResult:
        capabilities = self.runtime_registry.resolve_capabilities(profile)
        return RuntimeSelectionResult(
            binding=ResolvedRuntimeBinding(
                selected_profile_id=profile.profile_id,
                adapter_kind=profile.adapter_kind,
                provider_kind=profile.provider_kind,
                model_name=profile.model_name,
                resolved_capabilities=capabilities,
                fallback_used=fallback_used,
                selection_reason=selection_reason,
            ),
            profile=profile,
        )


def get_runtime_resolver() -> RuntimeResolver:
    return RuntimeResolver(
        runtime_registry=get_runtime_registry(),
        profile_registry=get_runtime_profile_registry(),
    )
