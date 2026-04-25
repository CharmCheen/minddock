"""Unit tests for the citation builder in grounded_generation."""

from app.rag.retrieval_models import RetrievedChunk
from app.services.grounded_generation import build_citation


def _make_hit(**overrides: object) -> RetrievedChunk:
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
    return RetrievedChunk(**defaults)


def test_build_citation_contains_all_required_fields() -> None:
    citation = build_citation(_make_hit()).to_api_dict()
    assert citation["doc_id"] == "d1"
    assert citation["chunk_id"] == "c1"
    assert citation["source"] == "kb/doc.md"
    assert isinstance(citation["snippet"], str)
    assert len(citation["snippet"]) > 0


def test_build_citation_page_is_none_for_markdown() -> None:
    citation = build_citation(_make_hit()).to_api_dict()
    assert citation["page"] is None


def test_build_citation_page_is_int_when_present() -> None:
    citation = build_citation(_make_hit(page=7)).to_api_dict()
    assert citation["page"] == 7


def test_build_citation_anchor_is_none_by_default() -> None:
    citation = build_citation(_make_hit()).to_api_dict()
    assert citation["anchor"] is None


def test_build_citation_anchor_preserves_value() -> None:
    citation = build_citation(_make_hit(anchor="section-storage")).to_api_dict()
    assert citation["anchor"] == "section-storage"


def test_build_citation_anchor_empty_string_becomes_none() -> None:
    citation = build_citation(_make_hit(anchor="")).to_api_dict()
    assert citation["anchor"] is None


def test_build_citation_snippet_is_truncated() -> None:
    long_text = "A" * 200
    citation = build_citation(_make_hit(text=long_text)).to_api_dict()
    assert len(citation["snippet"]) <= 120


def test_build_citation_preserves_title_section_location_ref() -> None:
    citation = build_citation(_make_hit()).to_api_dict()
    assert citation["title"] == "doc"
    assert citation["section"] == "Storage"
    assert citation["location"] == "Storage"
    assert citation["ref"] == "doc > Storage"


def test_build_citation_ref_fallback_to_title() -> None:
    citation = build_citation(_make_hit(ref="", title="fallback_title")).to_api_dict()
    assert citation["ref"] == "fallback_title"


def test_build_citation_ref_fallback_to_source() -> None:
    citation = build_citation(_make_hit(ref="", title="")).to_api_dict()
    assert citation["ref"] == "kb/doc.md"


def test_build_citation_raw_hit_uses_hit_only_window_defaults() -> None:
    citation = build_citation(_make_hit(page=3)).to_api_dict()

    assert citation["hit_chunk_id"] == "c1"
    assert citation["window_chunk_ids"] == ["c1"]
    assert citation["hit_in_window"] is True
    assert citation["window_chunk_count"] == 1
    assert citation["is_windowed"] is False
    assert citation["is_hit_only_fallback"] is True
    assert citation["hit_page"] == 3
    assert citation["citation_label"] == "Storage · p.3"


def test_build_citation_preserves_window_verifiability_metadata() -> None:
    citation = build_citation(
        _make_hit(
            page=5,
            extra_metadata={
                "hit_chunk_id": "c2",
                "window_chunk_ids": ["c1", "c2", "c3"],
                "page_start": 5,
                "page_end": 6,
                "section_title": "方法设计",
                "block_types": ["paragraph", "list_item"],
                "order_in_doc": 9,
                "block_type": "paragraph",
                "evidence_window_reason": "neighbor",
            },
        )
    ).to_api_dict()

    assert citation["hit_chunk_id"] == "c2"
    assert citation["window_chunk_ids"] == ["c1", "c2", "c3"]
    assert citation["hit_in_window"] is True
    assert citation["window_chunk_count"] == 3
    assert citation["is_windowed"] is True
    assert citation["is_hit_only_fallback"] is False
    assert citation["hit_page"] == 5
    assert citation["hit_order_in_doc"] == 9
    assert citation["hit_block_type"] == "paragraph"
    assert citation["evidence_window_reason"] == "neighbor"
    assert citation["citation_label"] == "方法设计 · pp.5-6"


def test_build_citation_table_caption_label() -> None:
    citation = build_citation(
        _make_hit(
            page=7,
            extra_metadata={
                "hit_chunk_id": "c1",
                "window_chunk_ids": ["c0", "c1"],
                "page_start": 7,
                "page_end": 7,
                "section_title": "Results",
                "block_types": ["caption", "table"],
                "evidence_window_reason": "table_caption",
            },
        )
    ).to_api_dict()

    assert citation["citation_label"] == "Table / Caption · p.7"


def test_build_citation_label_falls_back_to_section_without_page() -> None:
    citation = build_citation(_make_hit(page=None, section="方法设计")).to_api_dict()
    assert citation["citation_label"] == "方法设计"


def test_build_citation_evidence_preview_cleans_and_truncates_window_text() -> None:
    text = ("Line one\n\nLine two   " * 30).strip()
    citation = build_citation(_make_hit(text=text)).to_api_dict()

    assert citation["evidence_preview"]
    assert "\n" not in citation["evidence_preview"]
    assert "  " not in citation["evidence_preview"]
    assert len(citation["evidence_preview"]) <= 220
