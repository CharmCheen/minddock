"""PDF text extraction with per-page output.

Uses pymupdf (import as ``pymupdf``) for reliable text extraction from
text-based PDFs.  Scanned / image-only PDFs are detected and logged as
warnings — OCR is **not** in scope for Week 2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum characters on a page to consider it "has text"
_MIN_PAGE_TEXT_LENGTH = 20


@dataclass(frozen=True)
class PageText:
    """Text content of a single PDF page."""

    page: int          # 1-based page number
    text: str          # extracted plain text


def extract_pages(path: Path) -> list[PageText]:
    """Extract text from each page of a PDF file.

    Args:
        path: Absolute or relative path to a ``.pdf`` file.

    Returns:
        List of ``PageText`` objects, one per page that contains
        extractable text.  Pages with fewer than
        ``_MIN_PAGE_TEXT_LENGTH`` characters are skipped with a
        warning (likely scanned / image-only).

    Raises:
        RuntimeError: If pymupdf cannot open the file at all.
    """
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "pymupdf is required for PDF ingestion. "
            "Install it with `pip install pymupdf`."
        ) from exc

    pages: list[PageText] = []

    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:
        logger.error("Failed to open PDF: path=%s error=%s", path, exc)
        raise RuntimeError(f"Cannot open PDF: {path}") from exc

    total_pages = len(doc)
    skipped = 0

    for page_index in range(total_pages):
        page = doc[page_index]
        text = page.get_text("text").strip()

        if len(text) < _MIN_PAGE_TEXT_LENGTH:
            skipped += 1
            logger.warning(
                "PDF page has insufficient text (likely scanned/image): "
                "path=%s page=%d chars=%d",
                path, page_index + 1, len(text),
            )
            continue

        pages.append(PageText(page=page_index + 1, text=text))

    doc.close()

    logger.info(
        "PDF extracted: path=%s total_pages=%d extracted=%d skipped=%d",
        path, total_pages, len(pages), skipped,
    )

    return pages
