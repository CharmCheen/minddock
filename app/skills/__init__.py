"""Skill package exports with lazy loading to avoid cross-layer import cycles."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "SkillCapabilityTag",
    "SkillCatalogDetail",
    "SkillCatalogEntry",
    "SkillDescriptor",
    "SkillExecutionContext",
    "SkillInputSchema",
    "SkillInvocationMode",
    "SkillInvocationRequest",
    "SkillInvocationResult",
    "SkillInvocationSource",
    "SkillOutputSchema",
    "SkillRegistry",
    "SkillRequest",
    "SkillResult",
    "SkillSchemaField",
    "SkillSummary",
    "get_skill_registry",
]


def __getattr__(name: str):
    if name in {
        "SkillCapabilityTag",
        "SkillCatalogDetail",
        "SkillCatalogEntry",
        "SkillDescriptor",
        "SkillExecutionContext",
        "SkillInputSchema",
        "SkillInvocationMode",
        "SkillInvocationRequest",
        "SkillInvocationResult",
        "SkillInvocationSource",
        "SkillOutputSchema",
        "SkillRequest",
        "SkillResult",
        "SkillSchemaField",
        "SkillSummary",
    }:
        module = import_module("app.skills.models")
        return getattr(module, name)
    if name in {"SkillRegistry", "get_skill_registry"}:
        module = import_module("app.skills.registry")
        return getattr(module, name)
    raise AttributeError(name)
