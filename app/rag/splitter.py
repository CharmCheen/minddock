"""Text splitting utilities for ingestion."""

from __future__ import annotations

import re
from collections.abc import Iterable

HEADING_RE = re.compile(r"^\s{0,3}(#{1,3})\s+(.*)$")


def _sections_from_text(text: str) -> list[dict[str, str | None]]:
    sections: list[dict[str, str | None]] = []
    current_lines: list[str] = []
    current_section: str | None = None

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({"section": current_section, "text": body})
        current_lines.clear()

    for raw_line in text.splitlines():
        heading_match = HEADING_RE.match(raw_line)
        if heading_match:
            flush()
            title = heading_match.group(2).strip()
            current_section = title or None
            continue

        if not raw_line.strip():
            flush()
            continue

        current_lines.append(raw_line)

    flush()

    if sections:
        return sections

    fallback = text.strip()
    return [{"section": None, "text": fallback}] if fallback else []


def _chunk_by_tokens(text: str, chunk_size: int, overlap: int) -> Iterable[str]:
    tokens = text.split()
    if len(tokens) > 1:
        if len(tokens) <= chunk_size:
            yield " ".join(tokens)
            return

        step = max(1, chunk_size - overlap)
        for start in range(0, len(tokens), step):
            window = tokens[start : start + chunk_size]
            if not window:
                break
            yield " ".join(window)
            if start + chunk_size >= len(tokens):
                break
        return

    length = len(text)
    if length <= chunk_size:
        if text.strip():
            yield text.strip()
        return

    step = max(1, chunk_size - overlap)
    for start in range(0, length, step):
        window = text[start : start + chunk_size].strip()
        if window:
            yield window
        if start + chunk_size >= length:
            break


def split_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[dict[str, str | None]]:
    """Split text into chunks with optional section metadata."""

    chunks: list[dict[str, str | None]] = []
    for section in _sections_from_text(text):
        for chunk in _chunk_by_tokens(str(section["text"]), chunk_size, overlap):
            chunks.append({"section": section["section"], "text": chunk})
    return chunks
