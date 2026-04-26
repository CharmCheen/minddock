from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.rag.source_skill_catalog import get_builtin_source_skill, list_builtin_source_skills
from app.skills.local_store import LocalSkillStore
from app.skills.source_registry import SourceSkillRegistry


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
        "capabilities": ["csv_rows_as_text"],
        "permissions": ["read_file", "write_index"],
        "config": {"max_rows": 500},
        "safety_notes": ["uses_builtin_handler"],
    }


def _registry(tmp_path) -> SourceSkillRegistry:
    return SourceSkillRegistry(local_store=LocalSkillStore(tmp_path / "skills"))


def test_list_skills_contains_builtin_implemented_and_future(tmp_path) -> None:
    registry = _registry(tmp_path)
    skills = registry.list_skills()
    ids = {skill.id for skill in skills}

    assert "csv.extract" in ids
    assert "url.extract" in ids
    assert "image.ocr" in ids
    assert "audio.transcribe" in ids


def test_list_implemented_skills_excludes_future(tmp_path) -> None:
    registry = _registry(tmp_path)
    ids = {skill.id for skill in registry.list_implemented_skills()}

    assert "csv.extract" in ids
    assert "audio.transcribe" not in ids


def test_local_registered_skill_appears_in_registry(tmp_path) -> None:
    registry = _registry(tmp_path)

    result = registry.register_manifest(_valid_manifest())
    skill = registry.get_skill("local.project_csv")

    assert result.ok is True
    assert skill is not None
    assert skill.status == "local"
    assert skill.handler == "csv.extract"
    assert skill.config == {"max_rows": 500}


def test_disabled_local_skill_status_is_preserved(tmp_path) -> None:
    registry = _registry(tmp_path)
    assert registry.register_manifest(_valid_manifest()).ok is True

    result = registry.disable_skill("local.project_csv")
    skill = registry.get_skill("local.project_csv")

    assert result.ok is True
    assert skill is not None
    assert skill.status == "disabled"
    assert skill.enabled is False


def test_enable_disable_only_allows_local_skills(tmp_path) -> None:
    registry = _registry(tmp_path)

    disable_builtin = registry.disable_skill("csv.extract")
    enable_future = registry.enable_skill("audio.transcribe")

    assert disable_builtin.ok is False
    assert "Only local skills can be disabled." in disable_builtin.errors
    assert enable_future.ok is False
    assert "Only local skills can be enabled." in enable_future.errors


def test_all_skill_ids_unique_and_json_serializable(tmp_path) -> None:
    registry = _registry(tmp_path)
    assert registry.register_manifest(_valid_manifest()).ok is True
    skills = registry.list_skills()
    ids = [skill.id for skill in skills]

    assert len(ids) == len(set(ids))
    json.dumps([skill.to_dict() for skill in skills])


def test_source_skill_catalog_compatibility_layer_still_works() -> None:
    skills = list_builtin_source_skills()
    csv_skill = get_builtin_source_skill("csv.extract")

    assert csv_skill is not None
    assert csv_skill.id == "csv.extract"
    assert "entrypoint" not in csv_skill.to_dict()
    assert any(skill.id == "image.ocr" for skill in skills)


def test_frontend_source_skills_api_lists_catalog(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MINDDOCK_SKILLS_DIR", str(tmp_path / "skills"))
    client = TestClient(app)

    response = client.get("/frontend/source-skills")

    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload["items"]}
    assert "csv.extract" in ids
    assert "audio.transcribe" in ids
    csv_item = next(item for item in payload["items"] if item["id"] == "csv.extract")
    assert csv_item["handler_name"] == "CSV Extraction"
    assert any(field["name"] == "max_rows" for field in csv_item["config_schema"])
    assert csv_item["executable"] is True


def test_frontend_source_skills_validate_and_register(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MINDDOCK_SKILLS_DIR", str(tmp_path / "skills"))
    client = TestClient(app)

    validate_response = client.post("/frontend/source-skills/validate", json={"manifest": _valid_manifest()})
    register_response = client.post("/frontend/source-skills/register", json={"manifest": _valid_manifest()})
    list_response = client.get("/frontend/source-skills")

    assert validate_response.status_code == 200
    assert validate_response.json()["ok"] is True
    assert register_response.status_code == 200
    assert register_response.json()["ok"] is True
    ids = {item["id"] for item in list_response.json()["items"]}
    local_item = next(item for item in list_response.json()["items"] if item["id"] == "local.project_csv")
    assert "local.project_csv" in ids
    assert local_item["bindable"] is True
    assert local_item["executable"] is False
    assert local_item["config_keys"] == ["max_rows"]


def test_frontend_source_skills_rejects_unsafe_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MINDDOCK_SKILLS_DIR", str(tmp_path / "skills"))
    client = TestClient(app)
    manifest = _valid_manifest()
    manifest["entrypoint"] = "evil.py"

    response = client.post("/frontend/source-skills/validate", json={"manifest": manifest})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert any("Arbitrary entrypoint" in error for error in response.json()["errors"])
