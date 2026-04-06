"""Formal runtime request/response, profile, and selection models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ports.llm import EvidenceItem, LLMProvider


@dataclass(frozen=True)
class RuntimeRequest:
    """Normalized generation request passed into a runtime adapter."""

    prompt: Any
    inputs: dict[str, object]
    fallback_query: str
    fallback_evidence: list[EvidenceItem]
    llm_override: LLMProvider | None = None


@dataclass(frozen=True)
class RuntimeResponse:
    """Normalized generation response returned by a runtime adapter."""

    text: str
    runtime_name: str
    provider_name: str
    used_fallback: bool = False
    debug_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Capability declaration exposed by a generation runtime."""

    supports_chat: bool = False
    supports_summarize: bool = False
    supports_structured_output: bool = False
    supports_tool_or_skill_invocation: bool = False
    supports_streaming: bool = False
    supports_json_mode: bool = False
    max_context: int | None = None
    provider_family: str | None = None

    def labels(self) -> tuple[str, ...]:
        """Return the enabled capability names for metadata/reporting."""

        labels: list[str] = []
        for name in (
            "supports_chat",
            "supports_summarize",
            "supports_structured_output",
            "supports_tool_or_skill_invocation",
            "supports_streaming",
            "supports_json_mode",
        ):
            if getattr(self, name):
                labels.append(name)
        if self.max_context is not None:
            labels.append(f"max_context:{self.max_context}")
        if self.provider_family:
            labels.append(f"provider_family:{self.provider_family}")
        return tuple(labels)

    def merged_with(self, override: "RuntimeCapabilities | None") -> "RuntimeCapabilities":
        """Merge capability overrides onto the current declaration."""

        if override is None:
            return self
        return RuntimeCapabilities(
            supports_chat=override.supports_chat or self.supports_chat,
            supports_summarize=override.supports_summarize or self.supports_summarize,
            supports_structured_output=override.supports_structured_output or self.supports_structured_output,
            supports_tool_or_skill_invocation=override.supports_tool_or_skill_invocation or self.supports_tool_or_skill_invocation,
            supports_streaming=override.supports_streaming or self.supports_streaming,
            supports_json_mode=override.supports_json_mode or self.supports_json_mode,
            max_context=override.max_context if override.max_context is not None else self.max_context,
            provider_family=override.provider_family or self.provider_family,
        )


class RuntimeSelectionMode(StrEnum):
    """How runtime profile selection should behave."""

    AUTO = "auto"
    PREFERRED = "preferred"
    STRICT = "strict"


class OptimizationTarget(StrEnum):
    """Selection optimization target."""

    LATENCY = "latency"
    QUALITY = "quality"
    COST = "cost"
    PRIVACY = "privacy"


class LocalityPreference(StrEnum):
    """Policy preference for local/cloud execution."""

    LOCAL_ONLY = "local_only"
    CLOUD_ALLOWED = "cloud_allowed"
    CLOUD_PREFERRED = "cloud_preferred"


@dataclass(frozen=True)
class RuntimeProfile:
    """Externalized runtime profile that binds policy-facing selection to one adapter."""

    profile_id: str
    display_name: str
    adapter_kind: str
    provider_kind: str
    model_name: str
    base_url: str | None = None
    api_key_env: str | None = None
    default_generation_params: dict[str, object] = field(default_factory=dict)
    declared_capabilities: RuntimeCapabilities | None = None
    tags: tuple[str, ...] = ()
    enabled: bool = True
    priority: int = 100


@dataclass(frozen=True)
class RuntimeProfileSummary:
    """Safe profile summary returned to frontend callers."""

    profile_id: str
    display_name: str
    provider_kind: str
    model_name: str
    tags: tuple[str, ...] = ()
    enabled: bool = True
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPolicy:
    """Application-facing execution policy for runtime resolution."""

    preferred_profile_id: str | None = None
    allowed_profile_ids: tuple[str, ...] = ()
    selection_mode: RuntimeSelectionMode = RuntimeSelectionMode.AUTO
    optimization_target: OptimizationTarget = OptimizationTarget.QUALITY
    locality_preference: LocalityPreference = LocalityPreference.CLOUD_ALLOWED
    require_skill_support: bool = False
    require_structured_output: bool = False
    require_citations: bool = False

    def describe(self) -> str:
        """Return a compact metadata-safe policy description."""

        parts = [
            f"selection_mode={self.selection_mode.value}",
            f"optimization_target={self.optimization_target.value}",
            f"locality_preference={self.locality_preference.value}",
        ]
        if self.preferred_profile_id:
            parts.append(f"preferred_profile_id={self.preferred_profile_id}")
        if self.allowed_profile_ids:
            parts.append(f"allowed_profile_ids={','.join(self.allowed_profile_ids)}")
        if self.require_skill_support:
            parts.append("require_skill_support=true")
        if self.require_structured_output:
            parts.append("require_structured_output=true")
        if self.require_citations:
            parts.append("require_citations=true")
        return ";".join(parts)


@dataclass(frozen=True)
class ResolvedRuntimeBinding:
    """Resolved runtime binding after profile selection."""

    selected_profile_id: str
    adapter_kind: str
    provider_kind: str
    model_name: str
    resolved_capabilities: RuntimeCapabilities
    fallback_used: bool = False
    selection_reason: str = ""


@dataclass(frozen=True)
class RuntimeSelectionPolicy:
    """Policy knobs for runtime selection."""

    require_structured_output: bool = False
    require_skill_invocation: bool = False


@dataclass(frozen=True)
class RuntimeSelectionRequest:
    """Normalized runtime selection request."""

    task_type: str
    output_mode: str = "text"
    citation_policy: str = "preferred"
    skill_policy: str = "disabled"
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    policy: RuntimeSelectionPolicy = field(default_factory=RuntimeSelectionPolicy)


@dataclass(frozen=True)
class RuntimeSelectionResult:
    """Selected runtime plus matched capabilities."""

    binding: ResolvedRuntimeBinding
    profile: RuntimeProfile
