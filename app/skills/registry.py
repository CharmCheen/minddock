"""Skill registry, typed validation, and example skills."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.core.exceptions import InvalidSkillInputError, SkillExecutionFailedError
from app.skills.models import (
    JsonValue,
    SkillCapabilityTag,
    SkillCatalogDetail,
    SkillCatalogEntry,
    SkillDescriptor,
    SkillError,
    SkillExecutionContext,
    SkillInputSchema,
    SkillInvocationMode,
    SkillInvocationRequest,
    SkillInvocationResult,
    SkillOutputSchema,
    SkillSchemaField,
)


class Skill(ABC):
    """Stable skill port for future runtime/tool integrations."""

    descriptor: SkillDescriptor

    @abstractmethod
    def execute(self, request: SkillInvocationRequest, context: SkillExecutionContext) -> SkillInvocationResult:
        """Execute the skill and return a structured result."""


class EchoSkill(Skill):
    """Minimal example skill used to validate the typed skill execution path."""

    descriptor = SkillDescriptor(
        skill_id="echo",
        display_name="Echo",
        description="Return the provided text payload without modification.",
        capability_tags=(SkillCapabilityTag.UTILITY,),
        input_schema=SkillInputSchema(
            schema_name="echo.input.v1",
            description="Echo the provided text back to the caller.",
            fields=(
                SkillSchemaField(
                    name="text",
                    field_type="string",
                    description="Text to echo back.",
                    required=True,
                ),
            ),
        ),
        output_schema=SkillOutputSchema(
            schema_name="echo.output.v1",
            description="Echo output payload.",
            fields=(
                SkillSchemaField(name="text", field_type="string", description="Echoed text."),
                SkillSchemaField(name="debug", field_type="boolean", description="Whether debug mode was enabled."),
            ),
        ),
        invocation_mode=SkillInvocationMode.ALLOWLISTED,
        produces_artifact_kind="skill_result",
        safety_notes=("No external side effects.",),
    )

    def execute(self, request: SkillInvocationRequest, context: SkillExecutionContext) -> SkillInvocationResult:
        text = str(request.arguments.get("text") or "")
        return SkillInvocationResult(
            skill_id=self.descriptor.skill_id,
            success=True,
            output={"text": text, "debug": context.debug},
            summary_text="Echo skill executed successfully.",
            artifact_projection_hint="skill_result",
            metadata={"invocation_source": request.invocation_source.value},
        )


class BulletNormalizeSkill(Skill):
    """Small but practical formatting skill with typed I/O."""

    descriptor = SkillDescriptor(
        skill_id="bullet_normalize",
        display_name="Bullet Normalize",
        description="Normalize plain lines into consistently bulleted markdown.",
        capability_tags=(SkillCapabilityTag.FORMATTING, SkillCapabilityTag.TRANSFORMATION),
        input_schema=SkillInputSchema(
            schema_name="bullet_normalize.input.v1",
            description="Normalize user-provided lines into markdown bullet points.",
            fields=(
                SkillSchemaField(
                    name="text",
                    field_type="string",
                    description="Multiline text to convert into bullets.",
                    required=True,
                ),
                SkillSchemaField(
                    name="marker",
                    field_type="string",
                    description="Bullet marker to prefix each normalized line.",
                    required=False,
                    enum_values=("-", "*", "+"),
                    default="-",
                ),
            ),
        ),
        output_schema=SkillOutputSchema(
            schema_name="bullet_normalize.output.v1",
            description="Normalized markdown bullet output.",
            fields=(
                SkillSchemaField(name="normalized_text", field_type="string", description="Normalized bullet markdown."),
                SkillSchemaField(name="items", field_type="array", items_type="string", description="Normalized bullet items."),
                SkillSchemaField(name="item_count", field_type="integer", description="Number of normalized bullet items."),
            ),
        ),
        invocation_mode=SkillInvocationMode.ALLOWLISTED,
        produces_artifact_kind="skill_result",
        safety_notes=("Pure formatting transform with no external I/O.",),
    )

    def execute(self, request: SkillInvocationRequest, context: SkillExecutionContext) -> SkillInvocationResult:
        marker = str(request.arguments.get("marker") or "-").strip() or "-"
        raw_text = str(request.arguments.get("text") or "")
        lines = [line.strip().lstrip("-*+ ").strip() for line in raw_text.splitlines()]
        items = [line for line in lines if line]
        normalized = "\n".join(f"{marker} {item}" for item in items)
        return SkillInvocationResult(
            skill_id=self.descriptor.skill_id,
            success=True,
            output={
                "normalized_text": normalized,
                "items": items,
                "item_count": len(items),
                "debug": context.debug,
            },
            summary_text="Bullet normalization completed.",
            artifact_projection_hint="skill_result",
            metadata={"invocation_source": request.invocation_source.value},
        )


@dataclass
class SkillRegistry:
    """Registry for typed skill descriptors and implementations."""

    skills: dict[str, Skill] = field(default_factory=dict)

    def register(self, skill: Skill) -> None:
        self.skills[skill.descriptor.skill_id] = skill

    def descriptors(self, *, public_only: bool = False, enabled_only: bool = False) -> tuple[SkillDescriptor, ...]:
        descriptors = [skill.descriptor for skill in self.skills.values()]
        if public_only:
            descriptors = [descriptor for descriptor in descriptors if descriptor.safe_for_public_listing]
        if enabled_only:
            descriptors = [descriptor for descriptor in descriptors if descriptor.enabled]
        return tuple(sorted(descriptors, key=lambda item: item.skill_id))

    def get_descriptor(self, skill_id: str) -> SkillDescriptor | None:
        skill = self.skills.get(skill_id)
        return None if skill is None else skill.descriptor

    def catalog(self, *, public_only: bool = True, enabled_only: bool = True) -> tuple[SkillCatalogEntry, ...]:
        return tuple(
            SkillCatalogEntry(
                skill_id=descriptor.skill_id,
                display_name=descriptor.display_name,
                description=descriptor.description,
                version=descriptor.version,
                capability_tags=tuple(tag.value for tag in descriptor.capability_tags),
                invocation_mode=descriptor.invocation_mode.value,
                enabled=descriptor.enabled,
                safe_for_public_listing=descriptor.safe_for_public_listing,
                produces_artifact_kind=descriptor.produces_artifact_kind,
            )
            for descriptor in self.descriptors(public_only=public_only, enabled_only=enabled_only)
        )

    def catalog_detail(self, skill_id: str) -> SkillCatalogDetail | None:
        descriptor = self.get_descriptor(skill_id)
        if descriptor is None:
            return None
        return SkillCatalogDetail(
            skill_id=descriptor.skill_id,
            display_name=descriptor.display_name,
            description=descriptor.description,
            version=descriptor.version,
            capability_tags=tuple(tag.value for tag in descriptor.capability_tags),
            invocation_mode=descriptor.invocation_mode.value,
            enabled=descriptor.enabled,
            safe_for_public_listing=descriptor.safe_for_public_listing,
            timeout_hint_ms=descriptor.timeout_hint_ms,
            produces_artifact_kind=descriptor.produces_artifact_kind,
            input_schema=descriptor.input_schema,
            output_schema=descriptor.output_schema,
            visibility_notes=descriptor.visibility_notes,
            safety_notes=descriptor.safety_notes,
        )

    def execute(
        self,
        request: SkillInvocationRequest,
        context: SkillExecutionContext | None = None,
    ) -> SkillInvocationResult:
        skill = self.skills.get(request.skill_id)
        if skill is None:
            raise SkillError(f"Unknown skill: {request.skill_id}")
        normalized_arguments = self.validate_arguments(skill.descriptor, request.arguments)
        normalized_request = SkillInvocationRequest(
            skill_id=request.skill_id,
            arguments=normalized_arguments,
            invocation_source=request.invocation_source,
            run_id=request.run_id,
            step_id=request.step_id,
            caller_context=request.caller_context,
        )
        try:
            return skill.execute(normalized_request, context or SkillExecutionContext())
        except InvalidSkillInputError:
            raise
        except SkillExecutionFailedError:
            raise
        except Exception as exc:  # pragma: no cover - safety wrapper
            raise SkillExecutionFailedError(
                detail=f"Skill '{request.skill_id}' failed during execution: {exc}"
            ) from exc

    def validate_arguments(self, descriptor: SkillDescriptor, arguments: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
        payload = dict(arguments or {})
        schema = descriptor.input_schema
        if schema is None:
            return payload
        normalized: dict[str, JsonValue] = {}
        for field in schema.fields:
            if field.name not in payload:
                if field.required and field.default is None:
                    raise InvalidSkillInputError(
                        detail=f"Skill '{descriptor.skill_id}' requires argument '{field.name}'."
                    )
                if field.default is not None:
                    normalized[field.name] = field.default
                continue
            value = payload[field.name]
            self._validate_field_value(descriptor.skill_id, field, value)
            normalized[field.name] = value
        extra_fields = sorted(set(payload) - {field.name for field in schema.fields})
        for name in extra_fields:
            normalized[name] = payload[name]
        return normalized

    @staticmethod
    def _validate_field_value(skill_id: str, field: SkillSchemaField, value: JsonValue) -> None:
        if field.field_type == "string":
            if not isinstance(value, str):
                raise InvalidSkillInputError(detail=f"Skill '{skill_id}' expects '{field.name}' to be a string.")
            if field.enum_values and value not in field.enum_values:
                raise InvalidSkillInputError(
                    detail=f"Skill '{skill_id}' expects '{field.name}' to be one of {', '.join(field.enum_values)}."
                )
            return
        if field.field_type == "boolean":
            if not isinstance(value, bool):
                raise InvalidSkillInputError(detail=f"Skill '{skill_id}' expects '{field.name}' to be a boolean.")
            return
        if field.field_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidSkillInputError(detail=f"Skill '{skill_id}' expects '{field.name}' to be an integer.")
            return
        if field.field_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise InvalidSkillInputError(detail=f"Skill '{skill_id}' expects '{field.name}' to be a number.")
            return
        if field.field_type == "array":
            if not isinstance(value, list):
                raise InvalidSkillInputError(detail=f"Skill '{skill_id}' expects '{field.name}' to be an array.")
            if field.items_type == "string" and not all(isinstance(item, str) for item in value):
                raise InvalidSkillInputError(
                    detail=f"Skill '{skill_id}' expects every item in '{field.name}' to be a string."
                )
            return
        if field.field_type == "object" and not isinstance(value, dict):
            raise InvalidSkillInputError(detail=f"Skill '{skill_id}' expects '{field.name}' to be an object.")


@lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(BulletNormalizeSkill())
    return registry
