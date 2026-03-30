"""Unit tests for the citation builder in grounded_generation."""

from app.services.grounded_generation import build_citation


def _make_hit(**overrides: object) -> dict[str, object]:
    """Build a minimal hit dict with sensible defaults."""
    defaults: dict[str, object] = {
        "text": "MindDock stores chunks in Chroma.",
        "doc_id": "d1",
        "chunk_id": "c1",
        "source": "kb/doc.md",
        "title": "doc",
        "section": "Storage",
        "location": "Storage",
        "ref": "doc > Storage",
        "page": None,
        "anchor": None,
        "distance": 0.2,
    }
    defaults.update(overrides)
    return defaults


def test_build_citation_contains_all_required_fields() -> None:
    citation = build_citation(_make_hit())
    assert citation["doc_id"] == "d1"
    assert citation["chunk_id"] == "c1"
    assert citation["source"] == "kb/doc.md"
    assert isinstance(citation["snippet"], str)
    assert len(citation["snippet"]) > 0


def test_build_citation_page_is_none_for_markdown() -> None:
    citation = build_citation(_make_hit())
    assert citation["page"] is None


def test_build_citation_page_is_int_when_present() -> None:
    citation = build_citation(_make_hit(page=7))
    assert citation["page"] == 7


def test_build_citation_page_handles_string_number() -> None:
    """page stored as string '3' in metadata should become int 3."""
    citation = build_citation(_make_hit(page="3"))
    assert citation["page"] == 3


def test_build_citation_page_invalid_becomes_none() -> None:
    citation = build_citation(_make_hit(page="not-a-number"))
    assert citation["page"] is None


def test_build_citation_anchor_is_none_by_default() -> None:
    citation = build_citation(_make_hit())
    assert citation["anchor"] is None


def test_build_citation_anchor_preserves_value() -> None:
    citation = build_citation(_make_hit(anchor="section-storage"))
    assert citation["anchor"] == "section-storage"


def test_build_citation_anchor_empty_string_becomes_none() -> None:
    citation = build_citation(_make_hit(anchor=""))
    assert citation["anchor"] is None


def test_build_citation_snippet_is_truncated() -> None:
    long_text = "A" * 200
    citation = build_citation(_make_hit(text=long_text))
    assert len(citation["snippet"]) <= 120


def test_build_citation_preserves_title_section_location_ref() -> None:
    citation = build_citation(_make_hit())
    assert citation["title"] == "doc"
    assert citation["section"] == "Storage"
    assert citation["location"] == "Storage"
    assert citation["ref"] == "doc > Storage"


def test_build_citation_ref_fallback_to_title() -> None:
    citation = build_citation(_make_hit(ref="", title="fallback_title"))
    assert citation["ref"] == "fallback_title"


def test_build_citation_ref_fallback_to_source() -> None:
    citation = build_citation(_make_hit(ref="", title=""))
    assert citation["ref"] == "kb/doc.md"
