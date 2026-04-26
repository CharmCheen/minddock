"""Resolve local source-skill manifests into trusted handler bindings.

Bindings are metadata only. They do not instantiate loaders, import user code,
or change how ingestion chooses a source loader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.rag.source_models import SourceDescriptor
from app.skills.handlers import get_trusted_source_handler, is_trusted_source_handler
from app.skills.source_registry import SourceSkillRegistry, get_source_skill_registry


@dataclass(frozen=True)
class SourceSkillBinding:
    skill_id: str
    skill_name: str
    skill_version: str
    skill_origin: str
    handler: str
    input_kinds: tuple[str, ...]
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceSkillBindingResolution:
    binding: SourceSkillBinding | None = None
    warning: str = ""
    reason: str = ""
    matches: tuple[str, ...] = ()


def resolve_source_skill_binding(
    source: str | Path | SourceDescriptor,
    loader_name: str | None = None,
    *,
    registry: SourceSkillRegistry | None = None,
) -> SourceSkillBinding | None:
    return resolve_source_skill_binding_with_reason(source, loader_name, registry=registry).binding


def resolve_source_skill_binding_with_reason(
    source: str | Path | SourceDescriptor,
    loader_name: str | None = None,
    *,
    registry: SourceSkillRegistry | None = None,
) -> SourceSkillBindingResolution:
    source_kind = _source_input_kind(source)
    if not source_kind:
        return SourceSkillBindingResolution(reason="unsupported_source_kind")

    registry = registry or get_source_skill_registry()
    matches: list[SourceSkillBinding] = []
    for skill in registry.list_local_skills():
        if not skill.enabled or skill.status != "local" or skill.kind != "source":
            continue
        if not skill.handler or not is_trusted_source_handler(skill.handler):
            continue
        handler = get_trusted_source_handler(skill.handler)
        if handler is None:
            continue
        if loader_name and handler.loader_name != loader_name:
            continue
        declared_input_kinds = skill.input_kinds or handler.input_kinds
        if source_kind not in {kind.lower() for kind in declared_input_kinds}:
            continue
        matches.append(
            SourceSkillBinding(
                skill_id=skill.id,
                skill_name=skill.name,
                skill_version=skill.version,
                skill_origin=skill.origin,
                handler=skill.handler,
                input_kinds=skill.input_kinds,
                config=dict(skill.config),
            )
        )

    if not matches:
        return SourceSkillBindingResolution(reason="no_matching_local_skill")
    match_ids = tuple(match.skill_id for match in matches)
    if len(matches) > 1:
        return SourceSkillBindingResolution(
            warning="ambiguous_local_skill_binding",
            reason="multiple_matching_local_skills",
            matches=match_ids,
        )
    return SourceSkillBindingResolution(binding=matches[0], reason="matched", matches=match_ids)


def _source_input_kind(source: str | Path | SourceDescriptor) -> str:
    if isinstance(source, SourceDescriptor):
        if source.source_type == "url":
            return "url"
        if source.local_path is not None:
            return source.local_path.suffix.lower()
        return Path(source.source).suffix.lower()
    if isinstance(source, Path):
        return source.suffix.lower()
    source_text = str(source)
    parsed = urlparse(source_text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return "url"
    return Path(source_text).suffix.lower()
