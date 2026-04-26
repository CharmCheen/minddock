"""Local source-skill manifest store.

The store persists declaration-only JSON manifests under ``skills/local`` or a
directory supplied by ``MINDDOCK_SKILLS_DIR``. It never imports or executes code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.skills.manifest import (
    SkillInfo,
    SkillManifestError,
    SkillManifestValidationResult,
    load_manifest_file,
    manifest_to_json_payload,
    validate_manifest,
)


DEFAULT_LOCAL_SKILLS_DIR = Path("skills/local")


@dataclass(frozen=True)
class LocalSkillStore:
    base_dir: Path | None = None

    @property
    def root(self) -> Path:
        if self.base_dir is not None:
            return self.base_dir.expanduser()
        configured = os.environ.get("MINDDOCK_SKILLS_DIR")
        if configured:
            return Path(configured).expanduser()
        return DEFAULT_LOCAL_SKILLS_DIR

    def list_local_skills(self) -> tuple[SkillInfo, ...]:
        skills: list[SkillInfo] = []
        root = self.root
        if not root.exists():
            return ()
        for manifest_path in sorted(root.glob("local.*/skill.json")):
            try:
                result = validate_manifest(load_manifest_file(manifest_path))
            except SkillManifestError:
                continue
            if result.ok and result.skill is not None:
                skills.append(result.skill)
        return tuple(skills)

    def get_local_skill(self, skill_id: str) -> SkillInfo | None:
        result = self.validate_registered(skill_id)
        if result.ok and result.skill is not None:
            return result.skill
        return None

    def validate_registered(self, skill_id: str) -> SkillManifestValidationResult:
        path = self._manifest_path(skill_id)
        if not path.exists():
            return SkillManifestValidationResult(ok=False, skill_id=skill_id, errors=("Local skill manifest not found.",))
        try:
            payload = load_manifest_file(path)
        except SkillManifestError as exc:
            return SkillManifestValidationResult(ok=False, skill_id=skill_id, errors=(str(exc),))
        return validate_manifest(payload)

    def register_manifest(self, payload: dict[str, Any]) -> SkillManifestValidationResult:
        result = validate_manifest(payload)
        if not result.ok or result.skill is None:
            return result
        path = self._manifest_path(result.skill.id)
        if path.exists():
            return SkillManifestValidationResult(
                ok=False,
                skill_id=result.skill.id,
                errors=("Local skill id already exists.",),
                warnings=result.warnings,
                executable=False,
                reason="Manifest failed validation.",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_manifest(path, manifest_to_json_payload(result.skill))
        return result

    def set_enabled(self, skill_id: str, enabled: bool) -> SkillManifestValidationResult:
        path = self._manifest_path(skill_id)
        if not path.exists():
            return SkillManifestValidationResult(ok=False, skill_id=skill_id, errors=("Local skill manifest not found.",))
        try:
            payload = load_manifest_file(path)
        except SkillManifestError as exc:
            return SkillManifestValidationResult(ok=False, skill_id=skill_id, errors=(str(exc),))
        payload["enabled"] = enabled
        result = validate_manifest(payload)
        if not result.ok:
            return result
        self._write_manifest(path, payload)
        return validate_manifest(payload)

    def _manifest_path(self, skill_id: str) -> Path:
        return self.root / skill_id / "skill.json"

    @staticmethod
    def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
