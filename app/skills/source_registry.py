"""Source-skill catalog registry with local manifest support.

This registry is separate from ``app.skills.registry.SkillRegistry``. It is a
catalog and manifest control plane only; it does not execute application skills
and does not participate in unified execution planning.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.rag.source_skill_catalog import SourceSkillInfo, list_builtin_source_skills
from app.skills.handlers import get_trusted_source_handler
from app.skills.local_store import LocalSkillStore
from app.skills.manifest import SkillInfo, SkillManifestValidationResult, validate_manifest


_FUTURE_SOURCE_SKILLS: tuple[SkillInfo, ...] = (
    SkillInfo(
        id="image.caption",
        name="Image Caption",
        kind="source",
        version="0.1.0",
        status="future",
        description="Generate descriptive captions for images.",
        input_kinds=(".png", ".jpg", ".jpeg", ".webp"),
        output_type="SourceLoadResult",
        source_media="image",
        source_kind="image_file",
        loader_name="image.caption",
        capabilities=("image_caption",),
        limitations=("not_implemented", "requires_vision_model"),
        enabled=False,
        origin="builtin",
    ),

    SkillInfo(
        id="js_url.render",
        name="JavaScript URL Rendering",
        kind="source",
        version="0.1.0",
        status="future",
        description="Render JavaScript-heavy web pages before extraction.",
        input_kinds=("url",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="web_page",
        loader_name="js_url.render",
        capabilities=("js_rendered_html",),
        limitations=("not_implemented", "requires_browser_runtime"),
        enabled=False,
        origin="builtin",
    ),
    SkillInfo(
        id="workflow.citation_audit",
        name="Citation Audit",
        kind="workflow",
        version="0.1.0",
        status="future",
        description="Audit answer citations against retrieved evidence.",
        capabilities=("citation_audit",),
        limitations=("not_implemented",),
        enabled=False,
        origin="builtin",
    ),
    SkillInfo(
        id="workflow.demo_validation",
        name="Demo Validation",
        kind="workflow",
        version="0.1.0",
        status="future",
        description="Validate demo flows and expected evidence coverage.",
        capabilities=("demo_validation",),
        limitations=("not_implemented",),
        enabled=False,
        origin="builtin",
    ),
    SkillInfo(
        id="workflow.rebuild_index",
        name="Rebuild Index Workflow",
        kind="workflow",
        version="0.1.0",
        status="future",
        description="Coordinate controlled full index rebuilds.",
        capabilities=("rebuild_index",),
        limitations=("not_implemented",),
        enabled=False,
        origin="builtin",
    ),
)


@dataclass
class SourceSkillRegistry:
    local_store: LocalSkillStore | None = None

    def __post_init__(self) -> None:
        if self.local_store is None:
            self.local_store = LocalSkillStore()

    def list_skills(self, *, include_future: bool = True, include_local: bool = True) -> tuple[SkillInfo, ...]:
        skills: list[SkillInfo] = [_from_builtin(skill) for skill in list_builtin_source_skills()]
        if include_local and self.local_store is not None:
            skills.extend(self.local_store.list_local_skills())
        if include_future:
            skills.extend(_FUTURE_SOURCE_SKILLS)
        return tuple(sorted(skills, key=lambda skill: (skill.origin != "builtin", skill.status, skill.id)))

    def get_skill(self, skill_id: str) -> SkillInfo | None:
        for skill in self.list_skills(include_future=True, include_local=True):
            if skill.id == skill_id:
                return skill
        return None

    def list_implemented_skills(self) -> tuple[SkillInfo, ...]:
        return tuple(skill for skill in self.list_skills(include_future=False, include_local=True) if skill.enabled and skill.status in {"implemented", "local"})

    def list_source_skills(self) -> tuple[SkillInfo, ...]:
        return tuple(skill for skill in self.list_skills() if skill.kind == "source")

    def list_local_skills(self) -> tuple[SkillInfo, ...]:
        if self.local_store is None:
            return ()
        return self.local_store.list_local_skills()

    def validate_manifest(self, payload: dict) -> SkillManifestValidationResult:
        return validate_manifest(payload)

    def register_manifest(self, payload: dict) -> SkillManifestValidationResult:
        assert self.local_store is not None
        return self.local_store.register_manifest(payload)

    def enable_skill(self, skill_id: str) -> SkillManifestValidationResult:
        if not skill_id.startswith("local."):
            return SkillManifestValidationResult(ok=False, skill_id=skill_id, errors=("Only local skills can be enabled.",))
        assert self.local_store is not None
        return self.local_store.set_enabled(skill_id, True)

    def disable_skill(self, skill_id: str) -> SkillManifestValidationResult:
        if not skill_id.startswith("local."):
            return SkillManifestValidationResult(ok=False, skill_id=skill_id, errors=("Only local skills can be disabled.",))
        assert self.local_store is not None
        return self.local_store.set_enabled(skill_id, False)

    def validate_skill_catalog(self) -> tuple[str, ...]:
        errors: list[str] = []
        ids = [skill.id for skill in self.list_skills()]
        duplicates = sorted({skill_id for skill_id in ids if ids.count(skill_id) > 1})
        if duplicates:
            errors.append(f"Duplicate skill ids: {', '.join(duplicates)}")
        return tuple(errors)


def _from_builtin(skill: SourceSkillInfo) -> SkillInfo:
    handler = get_trusted_source_handler(skill.id)
    return SkillInfo(
        id=skill.id,
        name=skill.name,
        kind="source",
        version=skill.version,
        status="implemented",
        description=f"Built-in source extraction skill for {skill.name}.",
        input_kinds=handler.input_kinds if handler is not None else skill.input_kinds,
        output_type=handler.output_type if handler is not None else skill.output_type,
        source_media=handler.source_media if handler is not None else skill.source_media,
        source_kind=handler.source_kind if handler is not None else skill.source_kind,
        loader_name=handler.loader_name if handler is not None else skill.loader_name,
        handler=skill.id,
        capabilities=handler.capabilities if handler is not None else skill.capabilities,
        providers=skill.providers,
        limitations=handler.limitations if handler is not None else skill.limitations,
        permissions=handler.permissions if handler is not None else (("read_file", "write_index") if skill.id.startswith("file.") or skill.id in {"csv.extract", "image.ocr"} else ("read_url", "write_index")),
        safety_notes=skill.notes,
        enabled=True,
        origin="builtin",
    )


def get_source_skill_registry() -> SourceSkillRegistry:
    return SourceSkillRegistry()
