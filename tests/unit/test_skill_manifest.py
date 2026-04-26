from __future__ import annotations

import json

import pytest

from app.skills.manifest import SkillManifestError, load_manifest_file, validate_manifest


def _valid_manifest() -> dict:
    return {
        "id": "local.project_csv",
        "name": "Project CSV Skill",
        "kind": "source",
        "version": "0.1.0",
        "description": "Convert project CSV rows into searchable text.",
        "handler": "csv.extract",
        "input_kinds": [".csv"],
        "output_type": "SourceLoadResult",
        "source_media": "text",
        "source_kind": "csv_file",
        "loader_name": "csv.extract",
        "permissions": ["read_file", "write_index"],
        "safety_notes": ["uses_builtin_handler"],
    }


def test_valid_local_manifest_passes_validation() -> None:
    result = validate_manifest(_valid_manifest())

    assert result.ok is True
    assert result.skill_id == "local.project_csv"
    assert result.executable is True
    assert result.skill is not None
    assert result.skill.handler == "csv.extract"
    assert result.skill.origin == "local"


def test_manifest_id_must_use_safe_local_prefix() -> None:
    payload = _valid_manifest()
    payload["id"] = "project_csv"

    result = validate_manifest(payload)

    assert result.ok is False
    assert any("local.<safe-id>" in error for error in result.errors)


@pytest.mark.parametrize(
    "skill_id",
    [
        "local../evil",
        "local.evil/skill",
        "local.evil\\skill",
        "C:\\evil",
        "/local.evil",
        "local..evil",
    ],
)
def test_manifest_id_rejects_path_traversal_and_pathlike_values(skill_id: str) -> None:
    payload = _valid_manifest()
    payload["id"] = skill_id

    result = validate_manifest(payload)

    assert result.ok is False


@pytest.mark.parametrize(
    "field",
    ["entrypoint", "module_path", "script_path", "python_path", "execute", "run", "subprocess", "env", "api_key", "secret", "token"],
)
def test_unsafe_fields_are_rejected(field: str) -> None:
    payload = _valid_manifest()
    payload[field] = "danger"

    result = validate_manifest(payload)

    assert result.ok is False
    assert "Arbitrary entrypoint is not allowed in Skill System v1.1." in result.errors


def test_untrusted_handler_is_rejected() -> None:
    payload = _valid_manifest()
    payload["handler"] = "custom.python.module"

    result = validate_manifest(payload)

    assert result.ok is False
    assert any("not a trusted built-in source handler" in error for error in result.errors)


def test_unsupported_permission_is_rejected() -> None:
    payload = _valid_manifest()
    payload["permissions"] = ["read_file", "read_env"]

    result = validate_manifest(payload)

    assert result.ok is False
    assert any("Unsupported permissions" in error for error in result.errors)
    assert any("Forbidden permissions" in error for error in result.errors)


def test_workflow_manifest_can_validate_but_is_display_only() -> None:
    payload = _valid_manifest()
    payload["id"] = "local.workflow_note"
    payload["kind"] = "workflow"

    result = validate_manifest(payload)

    assert result.ok is True
    assert result.executable is False
    assert "display-only" in result.reason


def test_skill_info_does_not_expose_entrypoint_or_module_path() -> None:
    result = validate_manifest(_valid_manifest())
    assert result.skill is not None

    payload = result.skill.to_dict()

    assert "entrypoint" not in payload
    assert "module_path" not in payload
    assert "script_path" not in payload
    assert "api_key" not in json.dumps(payload).lower()


def test_json_manifest_file_loads(tmp_path) -> None:
    path = tmp_path / "skill.json"
    path.write_text(json.dumps(_valid_manifest()), encoding="utf-8")

    payload = load_manifest_file(path)

    assert payload["id"] == "local.project_csv"


def test_yaml_manifest_file_is_rejected(tmp_path) -> None:
    path = tmp_path / "skill.yaml"
    path.write_text("id: local.project_csv\n", encoding="utf-8")

    with pytest.raises(SkillManifestError, match="YAML skill manifests are not supported"):
        load_manifest_file(path)
