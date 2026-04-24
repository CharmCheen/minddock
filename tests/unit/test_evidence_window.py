"""Unit tests for minimal evidence-window expansion."""

from app.rag.retrieval_models import RetrievedChunk
from app.services.grounded_generation import build_citation, expand_evidence_windows


def _chunk(
    index: int,
    text: str,
    *,
    block_type: str = "paragraph",
    section: str = "Methods",
    table_id: str = "",
    page_start: int = 2,
    page_end: int = 2,
) -> RetrievedChunk:
    extra_metadata: dict[str, object] = {
        "order_in_doc": index,
        "block_type": block_type,
        "section_title": section,
        "page_start": page_start,
        "page_end": page_end,
    }
    if table_id:
        extra_metadata["table_id"] = table_id
    return RetrievedChunk(
        text=text,
        doc_id="doc1",
        chunk_id=f"doc1:{index}",
        source="paper.pdf",
        section=section,
        page=page_start,
        extra_metadata=extra_metadata,
    )


def _neighbor_loader(chunks: list[RetrievedChunk]):
    by_order = {chunk.extra_metadata["order_in_doc"]: chunk for chunk in chunks}

    def load(hit: RetrievedChunk, before: int, after: int) -> list[RetrievedChunk]:
        center = int(hit.extra_metadata["order_in_doc"])
        return [
            by_order[index]
            for index in range(center - before, center + after + 1)
            if index in by_order
        ]

    return load


def test_paragraph_hit_expands_to_neighbor_window() -> None:
    chunks = [
        _chunk(0, "Previous definition."),
        _chunk(1, "The retrieved paragraph."),
        _chunk(2, "Following limitation."),
    ]

    expanded = expand_evidence_windows([chunks[1]], neighbor_loader=_neighbor_loader(chunks))

    assert len(expanded) == 1
    assert expanded[0].extra_metadata["hit_chunk_id"] == "doc1:1"
    assert expanded[0].extra_metadata["window_chunk_ids"] == ["doc1:0", "doc1:1", "doc1:2"]
    assert "Previous definition." in expanded[0].text
    assert "Following limitation." in expanded[0].text


def test_heading_hit_uses_following_body_without_previous_context() -> None:
    chunks = [
        _chunk(0, "Prior section text.", section="Intro"),
        _chunk(1, "Method", block_type="heading"),
        _chunk(2, "The method is defined here."),
        _chunk(3, "More method detail."),
    ]

    expanded = expand_evidence_windows([chunks[1]], neighbor_loader=_neighbor_loader(chunks))

    assert expanded[0].extra_metadata["window_chunk_ids"] == ["doc1:1", "doc1:2", "doc1:3"]
    assert "Prior section text." not in expanded[0].text
    assert "The method is defined here." in expanded[0].text


def test_table_hit_binds_adjacent_caption() -> None:
    chunks = [
        _chunk(0, "Table 1 reports accuracy.", block_type="caption", table_id="tbl-1"),
        _chunk(1, "Model | Accuracy\nA | 90", block_type="table", table_id="tbl-1"),
    ]

    expanded = expand_evidence_windows([chunks[1]], neighbor_loader=_neighbor_loader(chunks))
    citation = build_citation(expanded[0]).to_api_dict()

    assert expanded[0].extra_metadata["window_chunk_ids"] == ["doc1:0", "doc1:1"]
    assert citation["table_id"] == "tbl-1"
    assert citation["block_types"] == ["caption", "table"]


def test_overlapping_windows_are_merged_and_deduped() -> None:
    chunks = [
        _chunk(0, "A"),
        _chunk(1, "B"),
        _chunk(2, "C"),
        _chunk(3, "D"),
    ]

    expanded = expand_evidence_windows([chunks[1], chunks[2]], neighbor_loader=_neighbor_loader(chunks))

    assert len(expanded) == 1
    assert expanded[0].extra_metadata["window_chunk_ids"] == ["doc1:0", "doc1:1", "doc1:2", "doc1:3"]


def test_cap_keeps_primary_hit_when_previous_neighbor_is_large() -> None:
    chunks = [
        _chunk(0, "P" * 2200),
        _chunk(1, "H" * 400, page_start=3, page_end=3),
        _chunk(2, "N" * 400),
    ]

    expanded = expand_evidence_windows([chunks[1]], neighbor_loader=_neighbor_loader(chunks))
    window_ids = expanded[0].extra_metadata["window_chunk_ids"]

    assert expanded[0].extra_metadata["hit_chunk_id"] == "doc1:1"
    assert "doc1:1" in window_ids
    assert expanded[0].extra_metadata["page_start"] <= 3 <= expanded[0].extra_metadata["page_end"]


def test_merge_keeps_primary_hit_when_combined_window_is_capped() -> None:
    chunks = [
        _chunk(0, "A" * 1200),
        _chunk(1, "B" * 1200),
        _chunk(2, "C" * 1200, page_start=4, page_end=4),
        _chunk(3, "D" * 1200),
    ]

    expanded = expand_evidence_windows([chunks[2], chunks[1]], neighbor_loader=_neighbor_loader(chunks))

    assert len(expanded) == 1
    assert expanded[0].extra_metadata["hit_chunk_id"] == "doc1:2"
    assert "doc1:2" in expanded[0].extra_metadata["window_chunk_ids"]
    assert expanded[0].extra_metadata["page_start"] <= 4 <= expanded[0].extra_metadata["page_end"]


def test_missing_metadata_or_loader_failure_falls_back_to_hit_only() -> None:
    hit = RetrievedChunk(text="Only hit.", doc_id="doc1", chunk_id="doc1:x", source="paper.pdf")

    def failing_loader(hit: RetrievedChunk, before: int, after: int) -> list[RetrievedChunk]:
        raise RuntimeError("metadata unavailable")

    expanded = expand_evidence_windows([hit], neighbor_loader=failing_loader)

    assert len(expanded) == 1
    assert expanded[0].text == "Only hit."
    assert expanded[0].extra_metadata["window_chunk_ids"] == ["doc1:x"]
