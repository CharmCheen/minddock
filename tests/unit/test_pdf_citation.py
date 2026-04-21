"""Tests verifying PDF citations carry real page numbers through the full pipeline."""

from app.rag.retrieval_models import RetrievedChunk
from app.services.grounded_generation import build_citation


def _make_pdf_hit(**overrides: object) -> RetrievedChunk:
    defaults: dict[str, object] = {
        "text": "RAG combines retrieval with generation for grounded answers.",
        "doc_id": "pdf_d1",
        "chunk_id": "pdf_d1:0",
        "source": "knowledge_management.pdf",
        "title": "knowledge_management",
        "section": "",
        "location": "page 2",
        "ref": "knowledge_management > page 2",
        "page": 2,
        "anchor": "",
        "distance": 0.3,
    }
    defaults.update(overrides)
    return RetrievedChunk(**defaults)


def _make_md_hit(**overrides: object) -> RetrievedChunk:
    defaults: dict[str, object] = {
        "text": "MindDock stores chunks in Chroma.",
        "doc_id": "md_d1",
        "chunk_id": "md_d1:0",
        "source": "example.md",
        "title": "example",
        "section": "Storage",
        "location": "Storage",
        "ref": "example > Storage",
        "page": None,
        "anchor": "",
        "distance": 0.2,
    }
    defaults.update(overrides)
    return RetrievedChunk(**defaults)


def test_pdf_citation_page_is_real_integer() -> None:
    citation = build_citation(_make_pdf_hit()).to_api_dict()

    assert citation["page"] == 2
    assert isinstance(citation["page"], int)


def test_pdf_citation_page_from_various_pages() -> None:
    for page_num in [1, 5, 42, 100]:
        citation = build_citation(_make_pdf_hit(page=page_num)).to_api_dict()
        assert citation["page"] == page_num


def test_pdf_citation_has_all_required_fields() -> None:
    citation = build_citation(_make_pdf_hit()).to_api_dict()

    assert citation["doc_id"] == "pdf_d1"
    assert citation["chunk_id"] == "pdf_d1:0"
    assert citation["source"] == "knowledge_management.pdf"
    assert isinstance(citation["snippet"], str)
    assert len(citation["snippet"]) > 0
    assert citation["page"] == 2
    assert citation["anchor"] is None
    assert citation["title"] == "knowledge_management"
    assert citation["location"] == "page 2"
    assert citation["ref"] == "knowledge_management > page 2"


def test_md_citation_page_is_none() -> None:
    citation = build_citation(_make_md_hit()).to_api_dict()

    assert citation["page"] is None


def test_md_citation_has_section() -> None:
    citation = build_citation(_make_md_hit()).to_api_dict()

    assert citation["section"] == "Storage"
    assert citation["ref"] == "example > Storage"


def test_pdf_and_md_citations_coexist() -> None:
    pdf_citation = build_citation(_make_pdf_hit(page=7)).to_api_dict()
    md_citation = build_citation(_make_md_hit()).to_api_dict()

    assert pdf_citation["page"] == 7
    assert md_citation["page"] is None
    assert pdf_citation["source"].endswith(".pdf")
    assert md_citation["source"].endswith(".md")
