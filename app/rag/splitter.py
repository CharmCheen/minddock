"""Text splitting utilities for ingestion.

Semantic-aware chunking for plain-text / markdown documents.
Uses the shared tokenizer for accurate token counting.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.rag._tokenizer import token_count

# ---------------------------------------------------------------------------
# Heading / block-type detection patterns
# ---------------------------------------------------------------------------

# Markdown headings: "# Title"
MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+)$")

# ALL-CAPS numbered section: "1 | INTRODUCTION"
ALL_CAPS_SECTION_RE = re.compile(r"^\s*\d+\s*\|\s*[A-Z][A-Z\s\-]{2,}$")

# Numbered section (English): "1. Introduction"
NUMBERED_SECTION_EN_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*\s+[A-Z][A-Za-z][A-Za-z\s\-]{2,}$"
)

# Numbered section (Chinese): "一、概述" or "第一章 总则"
NUMBERED_SECTION_ZH_RE = re.compile(
    r"^\s*[一-鿿一二三四五六七八九十零〇百千万]+[、、.\s]+[一-鿿A-Za-z0-9]{1,60}$"
)

# Sentence terminators for sentence-aware splitting
SENTENCE_TERMINATORS: frozenset[str] = frozenset(".!?;。！？；")


# ---------------------------------------------------------------------------
# Section extraction (enhanced heading detection)
# ---------------------------------------------------------------------------


def _sections_from_text(text: str) -> list[dict[str, str | None]]:
    """Split text into sections, detecting multiple heading patterns.

    Detects: markdown headings, ALL-CAPS dividers, numbered sections,
    and Chinese numbered sections.  Each section is emitted as a single
    paragraph for subsequent token-aware chunking.
    """
    sections: list[dict[str, str | None]] = []
    current_lines: list[str] = []
    current_section: str | None = None

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({"section": current_section, "text": body})
        current_lines.clear()

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        is_heading = False

        # Markdown heading
        md_match = MD_HEADING_RE.match(stripped)
        if md_match:
            flush()
            current_section = md_match.group(1).strip()
            is_heading = True

        # ALL-CAPS divider "1 | INTRODUCTION"
        elif ALL_CAPS_SECTION_RE.match(stripped):
            flush()
            current_section = stripped
            is_heading = True

        # Numbered English section "1. Introduction"
        elif NUMBERED_SECTION_EN_RE.match(stripped):
            flush()
            current_section = stripped
            is_heading = True

        # Numbered Chinese section "一、概述"
        elif NUMBERED_SECTION_ZH_RE.match(stripped):
            flush()
            current_section = stripped
            is_heading = True

        if is_heading:
            continue

        if not stripped:
            flush()
            continue

        current_lines.append(raw_line)

    flush()

    if sections:
        return sections

    fallback = text.strip()
    return [{"section": None, "text": fallback}] if fallback else []


# ---------------------------------------------------------------------------
# Sentence-aware sliding window
# ---------------------------------------------------------------------------


def _sentence_units(text: str) -> list[str]:
    """Split text into sentence units at sentence-ending punctuation."""
    units: list[str] = []
    start = 0
    text_len = len(text)
    for idx, ch in enumerate(text):
        if ch not in SENTENCE_TERMINATORS:
            continue
        end = idx + 1
        # Strip trailing ASCII closing punctuation
        while end < text_len and text[end] in "\"')\"":
            end += 1
        unit = text[start:end].strip()
        if unit:
            units.append(unit)
        start = end
    tail = text[start:].strip()
    if tail:
        units.append(tail)
    return units


def _char_windows_at_soft_boundaries(
    text: str, size: int, overlap: int
) -> list[str]:
    """Sliding window that prefers breaking at sentence boundaries."""
    step = max(1, size - overlap)
    windows: list[str] = []
    text_len = len(text)
    for start in range(0, text_len, step):
        end = min(start + size, text_len)
        if end < text_len:
            # Prefer breaking at a sentence terminator near the window end
            boundary = max(
                text.rfind(ch, start + int(size * 0.55), end)
                for ch in SENTENCE_TERMINATORS
            )
            if boundary > start:
                end = boundary + 1
        w = text[start:end].strip()
        if w:
            windows.append(w)
        if end >= text_len:
            break
    return windows


def _sentence_aware_window(
    text: str, size: int, overlap: int
) -> list[str]:
    """Split text into sentence-aware windows, respecting sentence boundaries."""
    units = _sentence_units(text)
    if len(units) <= 1:
        return _char_windows_at_soft_boundaries(text, size, overlap)

    windows: list[str] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        unit_len = len(unit)
        if unit_len > size:
            if current:
                windows.append(" ".join(current).strip())
                current = []
                current_len = 0
            windows.extend(_char_windows_at_soft_boundaries(unit, size, overlap))
            continue

        projected = current_len + unit_len + (1 if current else 0)
        if current and projected > size:
            windows.append(" ".join(current).strip())
            # Build overlap tail
            tail: list[str] = []
            tail_len = 0
            for prev in reversed(current):
                prev_len = len(prev) + (1 if tail else 0)
                if tail and tail_len + prev_len > overlap:
                    break
                tail.insert(0, prev)
                tail_len += prev_len
            current = tail
            current_len = tail_len

        current.append(unit)
        current_len += unit_len + (1 if current_len else 0)

    if current:
        window = " ".join(current).strip()
        if not windows or window != windows[-1]:
            windows.append(window)

    return [w for w in windows if w]


# ---------------------------------------------------------------------------
# Core chunking
# ---------------------------------------------------------------------------


def _chunk_by_tokens(text: str, chunk_size: int, overlap: int) -> Iterable[str]:
    """Split text into token-bounded, sentence-aware chunks.

    Uses the Qwen3 tokenizer for accurate token counting.
    Falls back to sentence/character boundaries when a unit exceeds chunk_size.
    """
    if not text.strip():
        return

    tok_count = token_count(text)
    if tok_count <= chunk_size:
        yield text.strip()
        return

    for window in _sentence_aware_window(text, chunk_size, overlap):
        if window.strip():
            yield window.strip()


def split_text(
    text: str, chunk_size: int = 380, overlap: int = 90
) -> list[dict[str, str | None]]:
    """Split text into semantically coherent chunks.

    Args:
        text: Input document text.
        chunk_size: Maximum tokens per chunk (default 380, matching
            structured_chunker.py CHUNK_MAX_TOKENS).
        overlap: Target overlap between adjacent chunks (default 90).

    Returns:
        List of dicts with ``section`` (section title or None) and
        ``text`` (chunk content).
    """
    chunks: list[dict[str, str | None]] = []
    for sec in _sections_from_text(text):
        sec_text = str(sec["text"] or "")
        for chunk_text in _chunk_by_tokens(sec_text, chunk_size, overlap):
            chunks.append({"section": sec["section"], "text": chunk_text})
    return chunks
