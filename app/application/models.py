"""Application-facing unified execution contract and planning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.application.artifacts import (
    ArtifactKind,
    BaseArtifact,
    MermaidArtifact,
    SearchResultsArtifact,
    SkillResultArtifact,
    StructuredJsonArtifact,
    TextArtifact,
)
from app.application.events import ExecutionEvent
from app.rag.retrieval_models import CitationRecord, GroundedAnswer, GroundedCompareResult, RetrievalFilters
from app.runtime.models import ExecutionPolicy
from app.services.service_models import ServiceIssue, UseCaseMetadata


class TaskType(StrEnum):
    """Supported frontend-facing execution task types."""

    CHAT = "chat"
    SUMMARIZE = "summarize"
    SEARCH = "search"
    COMPARE = "compare"
    STRUCTURED_GENERATION = "structured_generation"


class OutputMode(StrEnum):
    """Supported output rendering modes."""

    TEXT = "text"
    MERMAID = "mermaid"
    STRUCTURED = "structured"


class CitationPolicy(StrEnum):
    """Citation requirements exposed to the application layer."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    NONE = "none"


class SkillPolicyMode(StrEnum):
    """Skill-routing policy for unified execution."""

    DISABLED = "disabled"
    MANUAL_ONLY = "manual_only"
    ALLOWLISTED = "allowlisted"
    PLANNER_ALLOWED = "planner_allowed"
    RUNTIME_NATIVE_ALLOWED = "runtime_native_allowed"


class StepKind(StrEnum):
    """Logical step categories inside an execution plan."""

    RETRIEVE = "retrieve"
    RERANK = "rerank"
    COMPRESS = "compress"
    GENERATE = "generate"
    SUMMARIZE_MAP = "summarize_map"
    SUMMARIZE_REDUCE = "summarize_reduce"
    SKILL_INVOKE = "skill_invoke"
    FORMAT_OUTPUT = "format_output"


@dataclass(frozen=True, init=False)
class SkillPolicy:
    """Skill usage policy attached to a unified execution request."""

    mode: SkillPolicyMode = SkillPolicyMode.DISABLED
    allowed_skill_ids: tuple[str, ...] = ()
    denied_skill_ids: tuple[str, ...] = ()
    require_public_listing: bool = True
    allow_external_io: bool = False

    def __init__(
        self,
        mode: SkillPolicyMode = SkillPolicyMode.DISABLED,
        allowed_skill_ids: tuple[str, ...] = (),
        denied_skill_ids: tuple[str, ...] = (),
        require_public_listing: bool = True,
        allow_external_io: bool = False,
        allowlist: tuple[str, ...] | None = None,
    ) -> None:
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "allowed_skill_ids", allowed_skill_ids if allowlist is None else allowlist)
        object.__setattr__(self, "denied_skill_ids", denied_skill_ids)
        object.__setattr__(self, "require_public_listing", require_public_listing)
        object.__setattr__(self, "allow_external_io", allow_external_io)

    @property
    def allowlist(self) -> tuple[str, ...]:
        """Backward-compatible alias for earlier unified execution stages."""

        return self.allowed_skill_ids

    def describe(self) -> str:
        """Return a compact policy summary for metadata and debugging."""

        parts = [f"mode={self.mode.value}"]
        if self.allowed_skill_ids:
            parts.append(f"allowed={','.join(self.allowed_skill_ids)}")
        if self.denied_skill_ids:
            parts.append(f"denied={','.join(self.denied_skill_ids)}")
        if self.require_public_listing:
            parts.append("public_only=true")
        if self.allow_external_io:
            parts.append("external_io=true")
        return ";".join(parts)


@dataclass(frozen=True)
class RetrievalOptions:
    """Retrieval configuration kept at the application boundary."""

    top_k: int = 5
    filters: RetrievalFilters | None = None


@dataclass(frozen=True)
class UnifiedExecutionRequest:
    """Single application-facing request contract for frontend execution."""

    task_type: TaskType | None
    user_input: str
    retrieval: RetrievalOptions = field(default_factory=RetrievalOptions)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    output_mode: OutputMode = OutputMode.TEXT
    citation_policy: CitationPolicy = CitationPolicy.PREFERRED
    skill_policy: SkillPolicy = field(default_factory=SkillPolicy)
    requested_skill_id: str | None = None
    requested_skill_arguments: dict[str, object] = field(default_factory=dict)
    conversation_metadata: dict[str, object] = field(default_factory=dict)
    task_options: dict[str, object] = field(default_factory=dict)
    debug: bool = False
    include_metadata: bool = False
    include_events: bool = False


@dataclass(frozen=True)
class ExecutionStep:
    """One logical step in an application execution plan."""

    kind: StepKind
    name: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionDecision:
    """Planner-level decision summary before runtime selection."""

    requires_runtime: bool = True
    requires_structured_output: bool = False
    supports_citations: bool = True


@dataclass(frozen=True)
class ExecutionPlan:
    """Lightweight execution plan built by orchestrators."""

    task_type: TaskType
    steps: tuple[ExecutionStep, ...]
    decision: ExecutionDecision = field(default_factory=ExecutionDecision)


@dataclass(frozen=True)
class SkillInvocationRecord:
    """Serializable record of a skill invocation."""

    name: str
    ok: bool
    message: str | None = None
    output_preview: str | None = None


@dataclass(frozen=True)
class ExecutionSummary:
    """Execution summary returned alongside unified results."""

    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    selected_model_name: str | None = None
    selected_capabilities: tuple[str, ...] = ()
    fallback_used: bool = False
    selection_reason: str | None = None
    policy_applied: str | None = None
    execution_steps_executed: tuple[str, ...] = ()
    skill_invocations: tuple[SkillInvocationRecord, ...] = ()
    artifact_kinds_returned: tuple[str, ...] = ()
    primary_artifact_kind: str | None = None
    artifact_count: int = 0
    search_result_count: int = 0
    skill_artifact_count: int = 0
    warnings: tuple[str, ...] = ()
    issues: tuple[ServiceIssue, ...] = ()


@dataclass(frozen=True)
class UnifiedExecutionResponse:
    """Single application-facing execution response."""

    task_type: TaskType
    artifacts: tuple[BaseArtifact, ...]
    citations: tuple[CitationRecord, ...] = ()
    grounded_answer: GroundedAnswer | None = None
    compare_result: GroundedCompareResult | None = None
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)
    execution_summary: ExecutionSummary = field(default_factory=ExecutionSummary)
    run_id: str | None = None
    event_count: int = 0
    events: tuple[ExecutionEvent, ...] = ()

    @property
    def output_blocks(self) -> tuple[dict[str, object], ...]:
        """Compatibility projection for legacy output-block-oriented callers."""

        blocks: list[dict[str, object]] = []
        for artifact in self.artifacts:
            if isinstance(artifact, TextArtifact):
                blocks.append(
                    {
                        "kind": OutputMode.TEXT,
                        "content": artifact.text,
                        "title": artifact.title,
                        "metadata": artifact.metadata,
                    }
                )
            elif isinstance(artifact, MermaidArtifact):
                blocks.append(
                    {
                        "kind": OutputMode.MERMAID,
                        "content": artifact.mermaid_code,
                        "title": artifact.title,
                        "metadata": artifact.metadata,
                    }
                )
            elif isinstance(artifact, StructuredJsonArtifact):
                blocks.append(
                    {
                        "kind": OutputMode.STRUCTURED,
                        "content": str(artifact.data),
                        "title": artifact.title,
                        "metadata": artifact.metadata,
                    }
                )
            elif isinstance(artifact, SkillResultArtifact) and artifact.summary_text:
                blocks.append(
                    {
                        "kind": OutputMode.TEXT,
                        "content": artifact.summary_text,
                        "title": artifact.title,
                        "metadata": artifact.metadata,
                    }
                )
        return tuple(blocks)

    def primary_text(self) -> str:
        """Return the first text block or an empty string."""

        for artifact in self.artifacts:
            if isinstance(artifact, TextArtifact):
                return artifact.text
        return ""

    def primary_block(self, kind: OutputMode):
        """Return the first block matching the requested kind."""

        for artifact in self.artifacts:
            if kind == OutputMode.TEXT and isinstance(artifact, TextArtifact):
                return artifact
            if kind == OutputMode.MERMAID and isinstance(artifact, MermaidArtifact):
                return artifact
            if kind == OutputMode.STRUCTURED and isinstance(artifact, StructuredJsonArtifact):
                return artifact
        return None

    def metadata_dict(self) -> dict[str, Any]:
        """Expose lightweight metadata for presenter mapping."""

        return {
            "selected_runtime": self.metadata.selected_runtime,
            "selected_profile_id": self.metadata.selected_profile_id,
            "selected_provider_kind": self.metadata.selected_provider_kind,
            "selected_model_name": self.metadata.selected_model_name,
            "runtime_capabilities_matched": list(self.metadata.runtime_capabilities_matched),
            "resolved_capabilities": list(self.metadata.resolved_capabilities),
            "execution_steps_executed": list(self.metadata.execution_steps_executed),
            "artifact_kinds_returned": list(self.metadata.artifact_kinds_returned),
            "primary_artifact_kind": self.metadata.primary_artifact_kind,
            "artifact_count": self.metadata.artifact_count,
            "search_result_count": self.metadata.search_result_count,
            "skill_artifact_count": self.metadata.skill_artifact_count,
            "skill_invocations": [
                {
                    "name": item.name,
                    "ok": item.ok,
                    "message": item.message,
                    "output_preview": item.output_preview,
                }
                for item in self.metadata.skill_invocations
            ],
            "warnings": list(self.metadata.warnings),
            "issues": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity,
                    "source": item.source,
                }
                for item in self.metadata.issues
            ],
            "insufficient_evidence": self.metadata.insufficient_evidence,
            "support_status": self.metadata.support_status,
            "refusal_reason": self.metadata.refusal_reason,
            "partial_failure": self.metadata.partial_failure,
            "fallback_used": self.metadata.fallback_used,
            "selection_reason": self.metadata.selection_reason,
            "policy_applied": self.metadata.policy_applied,
            "filter_applied": self.metadata.filter_applied,
            "retrieval_stats": None
            if self.metadata.retrieval_stats is None
            else {
                "retrieved_hits": self.metadata.retrieval_stats.retrieved_hits,
                "grounded_hits": self.metadata.retrieval_stats.grounded_hits,
                "reranked_hits": self.metadata.retrieval_stats.reranked_hits,
                "returned_hits": self.metadata.retrieval_stats.returned_hits,
            },
        }
