"""Local source-skill manifest parsing and validation.

Skill System v1.1 intentionally accepts declaration-only manifests. A local
manifest may describe a source skill and bind it to a trusted built-in handler,
but it cannot provide executable code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.skills.handlers import (
    ALLOWED_SOURCE_SKILL_PERMISSIONS,
    DANGEROUS_MANIFEST_FIELDS,
    FORBIDDEN_SOURCE_SKILL_PERMISSIONS,
    TRUSTED_SOURCE_HANDLERS,
    validate_handler_config,
)

SkillKind = Literal["source", "workflow", "agent"]
SkillStatus = Literal["implemented", "local", "future", "experimental", "disabled", "invalid"]

_LOCAL_SKILL_ID_RE = re.compile(r"^local\.[a-z0-9][a-z0-9_.-]{0,80}$")
_PATHLIKE_RE = re.compile(r"(^[a-zA-Z]:)|[/\\]|(^|[.])\.\.([.]|$)")
_JSON_MANIFEST_NAMES = {"skill.json"}
_YAML_SUFFIXES = {".yaml", ".yml"}


@dataclass(frozen=True)
class SkillInfo:
    """Frontend-safe source skill metadata.

    This object is descriptive only. It intentionally has no executable
    entrypoint, Python module path, or arbitrary runtime hook.
    """

    id: str
    name: str
    kind: SkillKind
    version: str
    status: SkillStatus
    description: str
    input_kinds: tuple[str, ...] = ()
    output_type: str = ""
    source_media: str | None = None
    source_kind: str | None = None
    loader_name: str | None = None
    handler: str | None = None
    capabilities: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    origin: str = "builtin"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "status": self.status,
            "description": self.description,
            "input_kinds": list(self.input_kinds),
            "output_type": self.output_type,
            "source_media": self.source_media,
            "source_kind": self.source_kind,
            "loader_name": self.loader_name,
            "handler": self.handler,
            "capabilities": list(self.capabilities),
            "providers": list(self.providers),
            "limitations": list(self.limitations),
            "permissions": list(self.permissions),
            "safety_notes": list(self.safety_notes),
            "config_keys": sorted(self.config),
            "enabled": self.enabled,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class SkillManifestValidationResult:
    ok: bool
    skill_id: str | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    executable: bool = False
    reason: str = ""
    skill: SkillInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skill_id": self.skill_id,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "executable": self.executable,
            "reason": self.reason,
            "skill": None if self.skill is None else self.skill.to_dict(),
        }


class SkillManifestError(ValueError):
    """Raised when a local skill manifest cannot be parsed."""


def load_manifest_file(path: Path) -> dict[str, Any]:
    """Load a JSON manifest from disk.

    YAML is deliberately unsupported in v1.1 because PyYAML is not a project
    dependency and local registration should not expand the dependency surface.
    """

    if path.suffix.lower() in _YAML_SUFFIXES:
        raise SkillManifestError("YAML skill manifests are not supported in Skill System v1.1; use skill.json.")
    if path.name not in _JSON_MANIFEST_NAMES and path.suffix.lower() != ".json":
        raise SkillManifestError("Only JSON skill manifests are supported in Skill System v1.1.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillManifestError(f"Invalid JSON manifest: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise SkillManifestError("Skill manifest root must be a JSON object.")
    return payload


def validate_manifest(payload: dict[str, Any]) -> SkillManifestValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    lower_keys = {str(key).lower() for key in payload}
    forbidden = sorted(lower_keys & DANGEROUS_MANIFEST_FIELDS)
    if forbidden:
        errors.append("Arbitrary entrypoint is not allowed in Skill System v1.1.")
        errors.append(f"Forbidden manifest fields: {', '.join(forbidden)}")

    skill_id = _as_text(payload.get("id"))
    if not skill_id:
        errors.append("Manifest id is required.")
    elif not _is_safe_local_skill_id(skill_id):
        errors.append("Manifest id must match local.<safe-id> and cannot contain path traversal or path separators.")

    name = _as_text(payload.get("name")) or skill_id or "Unnamed Local Skill"
    kind = _as_text(payload.get("kind")) or "source"
    if kind not in {"source", "workflow", "agent"}:
        errors.append("Manifest kind must be one of: source, workflow, agent.")

    handler = _as_text(payload.get("handler"))
    if not handler:
        errors.append("Manifest handler is required.")
    elif handler not in TRUSTED_SOURCE_HANDLERS:
        errors.append(f"Handler '{handler}' is not a trusted built-in source handler.")

    config = payload.get("config", {})
    if config is None:
        config = {}
    if not isinstance(config, dict):
        errors.append("Manifest config must be an object.")
        config = {}
    elif handler:
        errors.extend(validate_handler_config(handler, config))

    permissions = _as_tuple(payload.get("permissions"))
    unsupported_permissions = sorted(set(permissions) - ALLOWED_SOURCE_SKILL_PERMISSIONS)
    forbidden_permissions = sorted(set(permissions) & FORBIDDEN_SOURCE_SKILL_PERMISSIONS)
    if unsupported_permissions:
        errors.append(f"Unsupported permissions: {', '.join(unsupported_permissions)}")
    if forbidden_permissions:
        errors.append(f"Forbidden permissions: {', '.join(forbidden_permissions)}")

    enabled = bool(payload.get("enabled", True))
    executable = kind == "source" and handler in TRUSTED_SOURCE_HANDLERS and enabled
    if kind != "source":
        executable = False
        warnings.append("Only source manifests can bind executable built-in source handlers in v1.1.")

    skill: SkillInfo | None = None
    if not errors:
        status: SkillStatus = "local" if enabled else "disabled"
        skill = SkillInfo(
            id=skill_id,
            name=name,
            kind=kind,  # type: ignore[arg-type]
            version=_as_text(payload.get("version")) or "0.1.0",
            status=status,
            description=_as_text(payload.get("description")) or "",
            input_kinds=_as_tuple(payload.get("input_kinds")),
            output_type=_as_text(payload.get("output_type")) or "SourceLoadResult",
            source_media=_as_optional_text(payload.get("source_media")),
            source_kind=_as_optional_text(payload.get("source_kind")),
            loader_name=_as_optional_text(payload.get("loader_name")),
            handler=handler,
            capabilities=_as_tuple(payload.get("capabilities")),
            providers=_as_tuple(payload.get("providers")),
            limitations=_as_tuple(payload.get("limitations")),
            permissions=permissions,
            safety_notes=_as_tuple(payload.get("safety_notes")),
            config=dict(config),
            enabled=enabled,
            origin="local",
        )

    reason = ""
    if errors:
        reason = "Manifest failed validation."
    elif executable:
        reason = f"Uses trusted built-in handler {handler}"
    else:
        reason = "Manifest is display-only in Skill System v1.1."

    return SkillManifestValidationResult(
        ok=not errors,
        skill_id=skill_id or None,
        errors=tuple(errors),
        warnings=tuple(dict.fromkeys(warnings)),
        executable=executable,
        reason=reason,
        skill=skill,
    )


def manifest_to_json_payload(skill: SkillInfo) -> dict[str, Any]:
    payload = {
        "id": skill.id,
        "name": skill.name,
        "kind": skill.kind,
        "version": skill.version,
        "description": skill.description,
        "handler": skill.handler,
        "input_kinds": list(skill.input_kinds),
        "output_type": skill.output_type,
        "source_media": skill.source_media,
        "source_kind": skill.source_kind,
        "loader_name": skill.loader_name,
        "capabilities": list(skill.capabilities),
        "providers": list(skill.providers),
        "limitations": list(skill.limitations),
        "permissions": list(skill.permissions),
        "safety_notes": list(skill.safety_notes),
        "config": dict(skill.config),
        "enabled": skill.enabled,
    }
    return {key: value for key, value in payload.items() if value not in (None, [], ())}


def _is_safe_local_skill_id(skill_id: str) -> bool:
    if not _LOCAL_SKILL_ID_RE.fullmatch(skill_id):
        return False
    return _PATHLIKE_RE.search(skill_id) is None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_optional_text(value: Any) -> str | None:
    text = _as_text(value)
    return text or None


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, list | tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()
