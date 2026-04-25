"""Tests for the built-in Source Skill Catalog.

These tests verify that the catalog is:
- read-only and descriptive
- contains only implemented skills
- contains no executable entrypoints or arbitrary paths
- serializable to JSON
- does not interfere with SourceLoaderRegistry behavior
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from app.rag.source_skill_catalog import (
    SourceSkillInfo,
    get_builtin_source_skill,
    list_builtin_source_skills,
)


# ---------------------------------------------------------------------------
# Catalog completeness
# ---------------------------------------------------------------------------


def test_list_builtin_source_skills_is_non_empty() -> None:
    skills = list_builtin_source_skills()
    assert len(skills) >= 1


def test_catalog_contains_url_extract() -> None:
    skills = list_builtin_source_skills()
    ids = {s.id for s in skills}
    assert "url.extract" in ids


def test_catalog_contains_image_ocr() -> None:
    skills = list_builtin_source_skills()
    ids = {s.id for s in skills}
    assert "image.ocr" in ids


def test_catalog_contains_pdf_markdown_text() -> None:
    skills = list_builtin_source_skills()
    ids = {s.id for s in skills}
    assert "file.pdf" in ids
    assert "file.markdown" in ids
    assert "file.text" in ids


def test_catalog_contains_csv_extract() -> None:
    skills = list_builtin_source_skills()
    ids = {s.id for s in skills}
    assert "csv.extract" in ids


# ---------------------------------------------------------------------------
# Skill structure invariants
# ---------------------------------------------------------------------------


def test_all_skill_ids_are_unique() -> None:
    skills = list_builtin_source_skills()
    ids = [s.id for s in skills]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_all_skill_kind_is_source() -> None:
    skills = list_builtin_source_skills()
    for skill in skills:
        assert skill.kind == "source", f"{skill.id} kind is {skill.kind!r}"


def test_all_output_type_is_source_load_result() -> None:
    skills = list_builtin_source_skills()
    for skill in skills:
        assert skill.output_type == "SourceLoadResult", f"{skill.id} output_type is {skill.output_type!r}"


# ---------------------------------------------------------------------------
# Specific skill metadata
# ---------------------------------------------------------------------------


def test_image_ocr_providers_include_mock_and_rapidocr() -> None:
    skill = get_builtin_source_skill("image.ocr")
    assert skill is not None
    providers = set(skill.providers)
    assert "mock" in providers
    assert "rapidocr" in providers


def test_url_extract_limitations_include_no_js_rendering() -> None:
    skill = get_builtin_source_skill("url.extract")
    assert skill is not None
    assert "no_js_rendering" in skill.limitations


def test_url_extract_has_expected_capabilities() -> None:
    skill = get_builtin_source_skill("url.extract")
    assert skill is not None
    caps = set(skill.capabilities)
    assert "static_html" in caps
    assert "title_extraction" in caps
    assert "main_text_extraction" in caps


def test_image_ocr_has_expected_limitations() -> None:
    skill = get_builtin_source_skill("image.ocr")
    assert skill is not None
    lims = set(skill.limitations)
    assert "no_image_caption" in lims
    assert "no_multimodal_embedding" in lims


def test_pdf_skill_has_citation_page_support() -> None:
    skill = get_builtin_source_skill("file.pdf")
    assert skill is not None
    assert "citation_page_support" in skill.capabilities


def test_csv_extract_output_type_is_source_load_result() -> None:
    skill = get_builtin_source_skill("csv.extract")
    assert skill is not None
    assert skill.output_type == "SourceLoadResult"


def test_csv_extract_limitations_include_no_excel() -> None:
    skill = get_builtin_source_skill("csv.extract")
    assert skill is not None
    assert "no_excel" in skill.limitations


def test_csv_extract_has_expected_capabilities() -> None:
    skill = get_builtin_source_skill("csv.extract")
    assert skill is not None
    caps = set(skill.capabilities)
    assert "csv_rows_as_text" in caps
    assert "header_detection" in caps
    assert "row_limit" in caps


# ---------------------------------------------------------------------------
# Safety: no executable or path fields
# ---------------------------------------------------------------------------


def test_skills_do_not_contain_executable_field() -> None:
    skills = list_builtin_source_skills()
    for skill in skills:
        d = skill.to_dict()
        forbidden = {"entrypoint", "execute", "callable", "module_path", "file_path", "python_path"}
        found = forbidden & set(d.keys())
        assert not found, f"{skill.id} contains forbidden keys: {found}"


def test_skills_do_not_contain_api_keys_or_secrets() -> None:
    skills = list_builtin_source_skills()
    for skill in skills:
        d = skill.to_dict()
        text = json.dumps(d).lower()
        assert "api_key" not in text
        assert "secret" not in text
        assert "token" not in text
        assert "password" not in text


# ---------------------------------------------------------------------------
# Future skills must NOT be in active catalog
# ---------------------------------------------------------------------------


def test_catalog_does_not_contain_future_skills() -> None:
    skills = list_builtin_source_skills()
    ids = {s.id for s in skills}
    future_ids = {"image.caption", "audio.transcribe", "video.transcribe"}
    overlap = ids & future_ids
    assert not overlap, f"future skills found in active catalog: {overlap}"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_catalog_is_json_serializable() -> None:
    skills = list_builtin_source_skills()
    payload = [s.to_dict() for s in skills]
    text = json.dumps(payload)
    restored = json.loads(text)
    assert len(restored) == len(skills)
    assert restored[0]["id"] == skills[0].id


def test_source_skill_info_is_frozen() -> None:
    skill = get_builtin_source_skill("file.text")
    assert skill is not None
    with pytest.raises(FrozenInstanceError):
        skill.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Lookup behavior
# ---------------------------------------------------------------------------


def test_get_builtin_source_skill_returns_none_for_unknown() -> None:
    assert get_builtin_source_skill("nonexistent.skill") is None


def test_get_builtin_source_skill_returns_skill_for_known() -> None:
    skill = get_builtin_source_skill("url.extract")
    assert skill is not None
    assert skill.id == "url.extract"
