"""PDF text extraction with per-page output and block-level structure.

Uses pymupdf (import as ``pymupdf``) for reliable text extraction from
text-based PDFs.  Scanned / image-only PDFs are detected and logged as
warnings — OCR is **not** in scope.

Provides two extraction modes:
- ``extract_pages()``  → list[PageText]  (plain text, backward-compatible)
- ``extract_page_blocks()`` → list[PageBlocks] (block-level dict for structured chunking)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Minimum characters on a page to consider it "has text"
_MIN_PAGE_TEXT_LENGTH = 20


@dataclass(frozen=True)
class PageText:
    """Text content of a single PDF page."""

    page: int          # 1-based page number
    text: str          # extracted plain text


@dataclass(frozen=True)
class PageBlocks:
    """Block-level content of a single PDF page."""

    page: int                         # 1-based page number
    text: str                         # plain concatenated text (for fallback)
    blocks: list[dict[str, Any]]      # pymupdf block dicts (type 0=text, 1=image, 2=math)


def extract_pages(path: Path) -> list[PageText]:
    """Extract plain text from each page of a PDF file.

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
    page_blocks_list = extract_page_blocks(path)
    return [
        PageText(page=pb.page, text=pb.text)
        for pb in page_blocks_list
        if len(pb.text.strip()) >= _MIN_PAGE_TEXT_LENGTH
    ]


def extract_page_blocks(path: Path) -> list[PageBlocks]:
    """Extract block-structured content from each page of a PDF file.

    This is the primary entry point for structured chunking. Each returned
    ``PageBlocks`` contains the raw pymupdf block list (including bbox and
    span-level information) that enables semantic type classification
    (heading, paragraph, table, caption, list, other).

    Args:
        path: Absolute or relative path to a ``.pdf`` file.

    Returns:
        List of ``PageBlocks`` objects, one per page. Pages with fewer than
        ``_MIN_PAGE_TEXT_LENGTH`` characters are included but flagged;
        the caller can skip them based on ``len(text) < _MIN_PAGE_TEXT_LENGTH``.

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

    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:
        logger.error("Failed to open PDF: path=%s error=%s", path, exc)
        raise RuntimeError(f"Cannot open PDF: {path}") from exc

    total_pages = len(doc)
    result: list[PageBlocks] = []

    for page_index in range(total_pages):
        page = doc[page_index]
        page_num = page_index + 1

        # Get block-level structure for semantic classification
        blocks: list[dict[str, Any]] = page.get_text("dict").get("blocks", [])

        # Get plain text for backward-compatible page text
        text = page.get_text("text").strip()

        if len(text) < _MIN_PAGE_TEXT_LENGTH:
            logger.warning(
                "PDF page has insufficient text (likely scanned/image): "
                "path=%s page=%d chars=%d",
                path, page_num, len(text),
            )

        result.append(PageBlocks(page=page_num, text=text, blocks=blocks))

    doc.close()

    logger.info(
        "PDF block-extracted: path=%s total_pages=%d",
        path, total_pages,
    )

    return result
