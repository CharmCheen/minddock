"""Unit tests for PDF document ingestion and page metadata."""

from pathlib import Path

from app.rag.ingest import build_document_payload


def _create_test_pdf(path: Path, pages_text: list[str]) -> None:
    """Create a minimal PDF with the given text on each page."""
    import pymupdf

    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), text, fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def test_pdf_ingest_produces_chunks_with_page_metadata(tmp_path: Path) -> None:
    """Each PDF chunk must carry a real page number in metadata."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    pdf_path = kb_dir / "demo.pdf"
    _create_test_pdf(pdf_path, [
        "Page one discusses retrieval augmented generation and how it helps ground AI answers.",
        "Page two covers vector databases like ChromaDB and their role in similarity search.",
    ])

    payload = build_document_payload(path=pdf_path, kb_dir=kb_dir)

    assert payload["doc_id"]
    assert len(payload["ids"]) >= 2  # at least 1 chunk per page
    assert len(payload["documents"]) >= 2
    assert len(payload["metadatas"]) >= 2

    # Verify each chunk has correct metadata
    for meta in payload["metadatas"]:
        assert meta["doc_id"] == payload["doc_id"]
        assert meta["source"] == "demo.pdf"
        assert meta["title"] == "demo"
        assert meta["page"] != ""  # must have a real page number
        assert int(meta["page"]) >= 1  # must be a valid page number


def test_pdf_chunks_have_correct_page_numbers(tmp_path: Path) -> None:
    """Chunks from page 1 should have page='1', etc."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    pdf_path = kb_dir / "pages.pdf"
    _create_test_pdf(pdf_path, [
        "First page content about knowledge management systems and personal productivity.",
        "Second page content about AI and machine learning in document retrieval.",
        "Third page content about citation tracking and evidence-based answers.",
    ])

    payload = build_document_payload(path=pdf_path, kb_dir=kb_dir)

    # Collect the page numbers from all chunks
    page_numbers = [meta["page"] for meta in payload["metadatas"]]

    # We should have chunks from pages 1, 2, and 3
    assert "1" in page_numbers
    assert "2" in page_numbers
    assert "3" in page_numbers


def test_pdf_metadata_location_and_ref_include_page(tmp_path: Path) -> None:
    """location and ref should reference the page number."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    pdf_path = kb_dir / "sample.pdf"
    _create_test_pdf(pdf_path, [
        "This is enough content on the first page to test metadata generation in the ingest pipeline.",
    ])

    payload = build_document_payload(path=pdf_path, kb_dir=kb_dir)

    meta = payload["metadatas"][0]
    assert "page 1" in meta["location"]
    assert "page 1" in meta["ref"]
    assert meta["title"] == "sample"


def test_pdf_ingest_handles_empty_pdf(tmp_path: Path) -> None:
    """A blank PDF should produce zero chunks, not crash."""
    import pymupdf

    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    pdf_path = kb_dir / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    doc.save(str(pdf_path))
    doc.close()

    payload = build_document_payload(path=pdf_path, kb_dir=kb_dir)

    assert payload["ids"] == []
    assert payload["documents"] == []
    assert payload["metadatas"] == []


def test_text_ingest_still_works_after_pdf_support(tmp_path: Path) -> None:
    """md/txt ingestion must remain unaffected."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    md_path = kb_dir / "notes.md"
    md_path.write_text("# Storage\nMindDock stores chunks in Chroma.\n", encoding="utf-8")

    payload = build_document_payload(path=md_path, kb_dir=kb_dir)

    assert payload["doc_id"]
    meta = payload["metadatas"][0]
    assert meta["source"] == "notes.md"
    assert meta["page"] == ""  # md has no page number
    assert meta["section"] == "Storage"
