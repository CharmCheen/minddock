"""Skill policy evaluation for unified execution."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.models import SkillPolicy, SkillPolicyMode
from app.core.exceptions import (
    SkillDisabledError,
    SkillInvocationModeMismatchError,
    SkillNotAllowlistedError,
    SkillNotFoundError,
    SkillNotPublicError,
)
from app.skills.models import (
    SkillCapabilityTag,
    SkillDescriptor,
    SkillInvocationMode,
    SkillInvocationSource,
)


@dataclass(frozen=True)
class SkillAccessDecision:
    """Structured skill access decision used at plan time and invocation time."""

    descriptor: SkillDescriptor
    invocation_source: SkillInvocationSource
    reason: str


@dataclass
class SkillAccessEvaluator:
    """Centralized evaluator for skill invocation policy checks."""

    registry: object

    def evaluate(
        self,
        *,
        skill_id: str,
        policy: SkillPolicy,
        invocation_source: SkillInvocationSource,
    ) -> SkillAccessDecision:
        descriptor = getattr(self.registry, "get_descriptor")(skill_id)
        if descriptor is None:
            raise SkillNotFoundError(detail=f"Skill '{skill_id}' was not found.")
        self._ensure_descriptor_accessible(descriptor=descriptor, policy=policy, invocation_source=invocation_source)
        return SkillAccessDecision(
            descriptor=descriptor,
            invocation_source=invocation_source,
            reason=f"{policy.mode.value}:{invocation_source.value}",
        )

    def resolve_requested_skills(
        self,
        *,
        requested_skill_id: str | None,
        policy: SkillPolicy,
    ) -> tuple[SkillAccessDecision, ...]:
        decisions: list[SkillAccessDecision] = []
        if requested_skill_id:
            decisions.append(
                self.evaluate(
                    skill_id=requested_skill_id,
                    policy=policy,
                    invocation_source=SkillInvocationSource.MANUAL,
                )
            )
            return tuple(decisions)

        if policy.mode == SkillPolicyMode.ALLOWLISTED:
            for skill_id in policy.allowed_skill_ids:
                decisions.append(
                    self.evaluate(
                        skill_id=skill_id,
                        policy=policy,
                        invocation_source=SkillInvocationSource.PLAN,
                    )
                )
        return tuple(decisions)

    def _ensure_descriptor_accessible(
        self,
        *,
        descriptor: SkillDescriptor,
        policy: SkillPolicy,
        invocation_source: SkillInvocationSource,
    ) -> None:
        if not descriptor.enabled or descriptor.invocation_mode == SkillInvocationMode.DISABLED:
            raise SkillDisabledError(detail=f"Skill '{descriptor.skill_id}' is disabled.")
        if policy.require_public_listing and not descriptor.safe_for_public_listing:
            raise SkillNotPublicError(detail=f"Skill '{descriptor.skill_id}' is not available for public listing.")
        if descriptor.skill_id in policy.denied_skill_ids:
            raise SkillNotAllowlistedError(detail=f"Skill '{descriptor.skill_id}' is denied by the active skill policy.")
        if SkillCapabilityTag.EXTERNAL_IO in descriptor.capability_tags and not policy.allow_external_io:
            raise SkillNotAllowlistedError(detail=f"Skill '{descriptor.skill_id}' requires external I/O, which is not allowed.")
        if policy.mode == SkillPolicyMode.DISABLED:
            raise SkillNotAllowlistedError(detail=f"Skill '{descriptor.skill_id}' is not allowed when skill policy is disabled.")
        if policy.mode == SkillPolicyMode.ALLOWLISTED and descriptor.skill_id not in policy.allowed_skill_ids:
            raise SkillNotAllowlistedError(detail=f"Skill '{descriptor.skill_id}' is not allowlisted by the active skill policy.")
        if policy.mode == SkillPolicyMode.MANUAL_ONLY and invocation_source != SkillInvocationSource.MANUAL:
            raise SkillInvocationModeMismatchError(
                detail=f"Skill '{descriptor.skill_id}' may only be invoked manually under the active skill policy."
            )
        if descriptor.invocation_mode == SkillInvocationMode.MANUAL_ONLY and invocation_source != SkillInvocationSource.MANUAL:
            raise SkillInvocationModeMismatchError(detail=f"Skill '{descriptor.skill_id}' only supports manual invocation.")
        if descriptor.invocation_mode == SkillInvocationMode.ALLOWLISTED and policy.mode != SkillPolicyMode.ALLOWLISTED:
            raise SkillInvocationModeMismatchError(
                detail=f"Skill '{descriptor.skill_id}' requires an allowlisted skill policy."
            )
        if descriptor.invocation_mode == SkillInvocationMode.PLANNER_ALLOWED and invocation_source not in {
            SkillInvocationSource.PLAN,
            SkillInvocationSource.PLANNER,
        }:
            raise SkillInvocationModeMismatchError(
                detail=f"Skill '{descriptor.skill_id}' only supports plan or planner invocation."
            )
        if descriptor.invocation_mode == SkillInvocationMode.RUNTIME_NATIVE_ALLOWED and invocation_source != SkillInvocationSource.RUNTIME_NATIVE:
            raise SkillInvocationModeMismatchError(
                detail=f"Skill '{descriptor.skill_id}' only supports runtime-native invocation."
            )

