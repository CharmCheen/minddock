"""Formal skill catalog, typed I/O, and invocation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


JsonValue = str | int | float | bool | None | dict[str, Any] | list[Any]


class SkillCapabilityTag(StrEnum):
    """Stable capability tags exposed in the skill catalog."""

    RETRIEVAL = "retrieval"
    TRANSFORMATION = "transformation"
    FORMATTING = "formatting"
    EXTERNAL_IO = "external_io"
    UTILITY = "utility"
    DIAGNOSTIC = "diagnostic"
    RUNTIME_NATIVE_TOOL = "runtime_native_tool"


class SkillInvocationMode(StrEnum):
    """How a skill may be invoked in the wider system."""

    DISABLED = "disabled"
    MANUAL_ONLY = "manual_only"
    ALLOWLISTED = "allowlisted"
    PLANNER_ALLOWED = "planner_allowed"
    RUNTIME_NATIVE_ALLOWED = "runtime_native_allowed"


class SkillInvocationSource(StrEnum):
    """Why a skill invocation was issued."""

    MANUAL = "manual"
    PLAN = "plan"
    PLANNER = "planner"
    RUNTIME_NATIVE = "runtime_native"


@dataclass(frozen=True)
class SkillSchemaField:
    """One JSON-compatible field in a skill input/output schema."""

    name: str
    field_type: str
    description: str
    required: bool = True
    enum_values: tuple[str, ...] = ()
    items_type: str | None = None
    default: JsonValue = None

    def summary(self) -> dict[str, JsonValue]:
        """Return a safe schema-field summary for outward mapping."""

        return {
            "name": self.name,
            "field_type": self.field_type,
            "description": self.description,
            "required": self.required,
            "enum_values": list(self.enum_values),
            "items_type": self.items_type,
            "default": self.default,
        }


@dataclass(frozen=True)
class SkillInputSchema:
    """Formal schema describing accepted skill input."""

    schema_name: str
    description: str
    fields: tuple[SkillSchemaField, ...] = ()


@dataclass(frozen=True)
class SkillOutputSchema:
    """Formal schema describing produced skill output."""

    schema_name: str
    description: str
    fields: tuple[SkillSchemaField, ...] = ()


@dataclass(frozen=True)
class SkillDescriptor:
    """Static skill metadata published by the registry and catalog."""

    skill_id: str
    display_name: str
    description: str
    version: str = "1.0.0"
    capability_tags: tuple[SkillCapabilityTag, ...] = ()
    input_schema_ref: str | None = None
    input_schema: SkillInputSchema | None = None
    output_schema_ref: str | None = None
    output_schema: SkillOutputSchema | None = None
    safe_for_public_listing: bool = True
    enabled: bool = True
    invocation_mode: SkillInvocationMode = SkillInvocationMode.MANUAL_ONLY
    timeout_hint_ms: int | None = None
    produces_artifact_kind: str | None = None
    visibility_notes: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        """Backward-compatible alias used by older tests and call sites."""

        return self.skill_id


@dataclass(frozen=True)
class SkillCatalogEntry:
    """Frontend-safe catalog entry for skill discovery."""

    skill_id: str
    display_name: str
    description: str
    version: str
    capability_tags: tuple[str, ...] = ()
    invocation_mode: str = SkillInvocationMode.MANUAL_ONLY.value
    enabled: bool = True
    safe_for_public_listing: bool = True
    produces_artifact_kind: str | None = None


@dataclass(frozen=True)
class SkillCatalogDetail:
    """Frontend-safe skill detail including schema summaries."""

    skill_id: str
    display_name: str
    description: str
    version: str
    capability_tags: tuple[str, ...] = ()
    invocation_mode: str = SkillInvocationMode.MANUAL_ONLY.value
    enabled: bool = True
    safe_for_public_listing: bool = True
    timeout_hint_ms: int | None = None
    produces_artifact_kind: str | None = None
    input_schema: SkillInputSchema | None = None
    output_schema: SkillOutputSchema | None = None
    visibility_notes: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillInvocationRequest:
    """Normalized, typed invocation request for one skill."""

    skill_id: str
    arguments: dict[str, JsonValue] = field(default_factory=dict)
    invocation_source: SkillInvocationSource = SkillInvocationSource.MANUAL
    run_id: str | None = None
    step_id: str | None = None
    caller_context: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Backward-compatible alias for legacy call sites."""

        return self.skill_id


@dataclass(frozen=True)
class SkillExecutionContext:
    """Shared execution context passed to skills."""

    request_id: str | None = None
    debug: bool = False


@dataclass(frozen=True)
class SkillInvocationResult:
    """Formal result returned by one typed skill invocation."""

    skill_id: str
    success: bool
    output: dict[str, JsonValue] = field(default_factory=dict)
    summary_text: str | None = None
    artifact_projection_hint: str | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    timing_ms: float | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Backward-compatible alias for legacy call sites."""

        return self.skill_id

    @property
    def ok(self) -> bool:
        """Backward-compatible alias for legacy call sites."""

        return self.success

    @property
    def message(self) -> str | None:
        """Backward-compatible alias for legacy call sites."""

        return self.summary_text


SkillRequest = SkillInvocationRequest
SkillResult = SkillInvocationResult
SkillSummary = SkillCatalogEntry


class SkillError(RuntimeError):
    """Raised when a registered skill cannot be executed safely."""

