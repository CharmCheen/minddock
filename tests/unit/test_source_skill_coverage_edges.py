from __future__ import annotations

import json

from app.skills.local_store import LocalSkillStore
from app.skills.manifest import SkillInfo
from app.skills.source_registry import SourceSkillRegistry


def _valid_manifest(skill_id: str = "local.project_csv") -> dict:
    return {
        "id": skill_id,
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
        "capabilities": ["csv_rows_as_text"],
        "permissions": ["read_file", "write_index"],
        "config": {"max_rows": 500},
        "safety_notes": ["uses_builtin_handler"],
    }


def test_local_skill_store_uses_env_root_and_reports_missing_manifest(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "configured-skills"
    monkeypatch.setenv("MINDDOCK_SKILLS_DIR", str(configured))
    store = LocalSkillStore()

    result = store.validate_registered("local.missing")

    assert store.root == configured
    assert result.ok is False
    assert result.errors == ("Local skill manifest not found.",)
    assert store.get_local_skill("local.missing") is None


def test_local_skill_store_lists_valid_manifests_and_ignores_invalid_json(tmp_path) -> None:
    root = tmp_path / "skills"
    valid_path = root / "local.good" / "skill.json"
    invalid_path = root / "local.bad" / "skill.json"
    valid_path.parent.mkdir(parents=True)
    invalid_path.parent.mkdir(parents=True)
    valid_path.write_text(json.dumps(_valid_manifest("local.good")), encoding="utf-8")
    invalid_path.write_text("{not-json", encoding="utf-8")

    skills = LocalSkillStore(root).list_local_skills()

    assert [skill.id for skill in skills] == ["local.good"]


def test_local_skill_store_rejects_duplicate_registration_and_missing_enable(tmp_path) -> None:
    store = LocalSkillStore(tmp_path / "skills")

    first = store.register_manifest(_valid_manifest())
    duplicate = store.register_manifest(_valid_manifest())
    missing_enable = store.set_enabled("local.missing", True)

    assert first.ok is True
    assert duplicate.ok is False
    assert duplicate.errors == ("Local skill id already exists.",)
    assert missing_enable.ok is False
    assert missing_enable.errors == ("Local skill manifest not found.",)


def test_source_skill_registry_flags_duplicate_ids_from_local_store(tmp_path) -> None:
    class DuplicateLocalStore:
        def list_local_skills(self):
            return (
                SkillInfo(
                    id="csv.extract",
                    name="Duplicate CSV",
                    kind="source",
                    version="0.1.0",
                    status="local",
                    description="Duplicate id for validation.",
                    input_kinds=(".csv",),
                    output_type="SourceLoadResult",
                    enabled=True,
                    origin="local",
                ),
            )

    registry = SourceSkillRegistry(local_store=DuplicateLocalStore())  # type: ignore[arg-type]

    assert registry.validate_skill_catalog() == ("Duplicate skill ids: csv.extract",)


def test_source_skill_registry_supports_listing_without_local_or_future_entries(tmp_path) -> None:
    registry = SourceSkillRegistry(local_store=LocalSkillStore(tmp_path / "skills"))
    registry.local_store = None

    builtin_only = registry.list_skills(include_future=False, include_local=False)

    assert registry.list_local_skills() == ()
    assert builtin_only
    assert all(skill.origin == "builtin" for skill in builtin_only)
    assert all(skill.status == "implemented" for skill in builtin_only)
