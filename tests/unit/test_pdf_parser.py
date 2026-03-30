"""Unit tests for PDF text extraction via pdf_parser."""

from pathlib import Path

import pytest

from app.rag.pdf_parser import PageText, extract_pages


def _create_test_pdf(path: Path, pages_text: list[str]) -> None:
    """Create a minimal PDF with the given text on each page."""
    import pymupdf

    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), text, fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def test_extract_pages_returns_all_text_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    _create_test_pdf(pdf_path, [
        "Page one has some content about knowledge management systems.",
        "Page two discusses vector databases and embeddings for search.",
        "Page three covers citation tracking and evidence grounding.",
    ])

    pages = extract_pages(pdf_path)

    assert len(pages) == 3
    assert pages[0].page == 1
    assert pages[1].page == 2
    assert pages[2].page == 3
    assert "knowledge management" in pages[0].text
    assert "vector databases" in pages[1].text
    assert "citation tracking" in pages[2].text


def test_extract_pages_returns_page_text_dataclass(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    _create_test_pdf(pdf_path, ["Enough text to pass the minimum threshold for page content."])

    pages = extract_pages(pdf_path)

    assert len(pages) == 1
    assert isinstance(pages[0], PageText)
    assert isinstance(pages[0].page, int)
    assert isinstance(pages[0].text, str)


def test_extract_pages_skips_empty_pages(tmp_path: Path) -> None:
    """Pages with less than _MIN_PAGE_TEXT_LENGTH chars are skipped."""
    import pymupdf

    pdf_path = tmp_path / "test.pdf"
    doc = pymupdf.open()
    # Page 1: has real content
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 72), "This page has enough text to be extracted properly by the parser.", fontsize=11)
    # Page 2: nearly empty (just "x")
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 72), "x", fontsize=11)
    # Page 3: has content
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((72, 72), "Third page with sufficient content for extraction testing.", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_pages(pdf_path)

    assert len(pages) == 2
    assert pages[0].page == 1
    assert pages[1].page == 3  # page 2 was skipped


def test_extract_pages_raises_on_invalid_file(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "not_really.pdf"
    fake_pdf.write_text("this is not a PDF", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Cannot open PDF"):
        extract_pages(fake_pdf)


def test_extract_pages_returns_empty_for_no_text_pdf(tmp_path: Path) -> None:
    """A PDF with only blank pages returns an empty list."""
    import pymupdf

    pdf_path = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)  # blank page
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_pages(pdf_path)

    assert pages == []
