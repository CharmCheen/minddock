"""Structured block extraction and semantic chunking for PDFs.

This module provides a two-stage pipeline:
1. Block extraction: raw PDF page text 鈫?typed blocks (heading, paragraph,
   table, caption, list, other)
2. Block-to-chunk conversion: typed blocks 鈫?semantically coherent chunks
   with rich metadata, using heading as anchor and sliding window as fallback.

The output format is compatible with the existing ingest pipeline so that
neither the vector-store adapter nor the search/chat routes need changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class BlockType(str, Enum):
    """Semantic type of a text block extracted from a PDF page."""

    # Document structure block types
    TITLE = "title"           # Document title (extracted from page 1)
    AUTHOR = "author"         # Author / affiliation lines
    ABSTRACT = "abstract"    # Abstract section text
    REFERENCE = "reference"   # Bibliography / references section
    # Content block types
    HEADING = "heading"      # Section / sub-section title
    PARAGRAPH = "paragraph"  # Body text
    TABLE_LIKE = "table"     # Tabular / pseudo-tabular content
    CAPTION = "caption"      # Figure / table caption text
    LIST_ITEM = "list_item"  # Bullet / numbered list entry
    OTHER = "other"          # Page number, footnote, header, etc.


@dataclass(frozen=True)
class PDFBlock:
    """A typed block extracted from a single PDF page."""

    block_type: BlockType
    text: str
    page: int               # 1-based page number
    block_index: int        # position on the page (0-based)
    heading_level: int = 0  # 1-6 for heading blocks, 0 otherwise
    raw_bboxes: tuple[str, ...] = field(default_factory=tuple)  # debug aid

    @property
    def is_visible(self) -> bool:
        """Skip page-artifact blocks (headers, footers, page numbers)."""
        return self.block_type not in {BlockType.OTHER} or len(self.text) > 3


@dataclass(frozen=True)
class ChunkMeta:
    """Rich metadata attached to every generated chunk."""

    doc_id: str
    chunk_id: str
    source: str
    source_path: str
    source_type: str
    title: str
    block_type: str           # title | author | abstract | heading | paragraph | table | caption | list_item | reference | other
    section_title: str        # nearest heading above this chunk
    table_id: str | None      # e.g. "表1" if a table caption was detected
    page_start: int
    page_end: int
    order_in_doc: int
    char_count: int
    token_estimate: int
    location: str
    ref: str
    source_version: str
    content_hash: str
    last_ingested_at: str
    ingest_status: str = "ready"
    # Fine-grained citation support
    block_ids: tuple[str, ...] = ()           # IDs of blocks that compose this chunk
    section_path: str | None = None            # Hierarchical path like "1.2.3" for sections
    semantic_type: str | None = None           # Derived semantic type (e.g., "abstract", "introduction")
    parent_block_id: str | None = None         # Parent block ID for hierarchical relationships
    child_block_ids: tuple[str, ...] = ()      # Child block IDs for hierarchical relationships


_CAPTION_NUM_RE = r"(?:\d+|[\u4e00-\u5341IVXivx]+)(?:[.\-–—_]\d+)*"

_CAPTION_START_RE = re.compile(
    rf"^\s*(?:\u56fe|\u8868|Figure|Fig\.?|Table)\s*{_CAPTION_NUM_RE}(?:[\.:：、]\s*|\s+.+)",
    re.IGNORECASE,
)

_TABLE_CAPTION_START_RE = re.compile(
    rf"^\s*(?:\u8868|Table)\s*{_CAPTION_NUM_RE}",
    re.IGNORECASE,
)

_FIGURE_CAPTION_START_RE = re.compile(
    rf"^\s*(?:\u56fe|Figure|Fig\.?)\s*{_CAPTION_NUM_RE}",
    re.IGNORECASE,
)

_ABSTRACT_MARKER_RE = re.compile(
    r"^\s*(?:Abstract|ABSTRACT|\u6458\s*\u8981)\s*[:：]?\s*(.*)$",
    re.IGNORECASE,
)

_KEYWORDS_MARKER_RE = re.compile(
    r"^\s*(?:Key\s+Words?(?:\s+and\s+Phrases)?|\u5173\u952e\u8bcd)\s*[:：]?\s*(.*)$",
    re.IGNORECASE,
)

_ALL_CAPS_SECTION_RE = re.compile(
    r"^\s*\d+\s*\|\s*[A-Z][A-Z\s\-]{2,}$"
)


# ---------------------------------------------------------------------------
# Configuration (闆嗕腑鍙皟鍙傛暟)
# ---------------------------------------------------------------------------

CHUNK_MAX_TOKENS: int = 600
CHUNK_MIN_TOKENS: int = 80
CHUNK_OVERLAP_TOKENS: int = 80
MAX_HEADING_CHARS: int = 200      # 瓒呰繃姝ら暱搴?heading 涔熷綋浣?paragraph 澶勭悊

TABLE_LINE_RATIO: float = 0.3
TABLE_MIN_ROWS: int = 2
TABLE_COL_SEPARATOR_CHARS: frozenset = frozenset("│|:\t")

HEADING_PATTERNS: list[re.Pattern[str]] = [
    # 1. 鑳屾櫙  2.鐩稿叧宸ヤ綔  (绔犺妭缂栧彿 + 绔犺妭鍚?
    re.compile(r"^\s*[\d锛愶紤锛掞紦锛旓紩锛栵紬锛橈紮]+\.[\s銆€]+(.+)"),
    # 1.1 鑳屾櫙  1.2.3 鐩稿叧宸ヤ綔  (澶氱骇缂栧彿)
    re.compile(r"^\s*[\d锛愶紤锛掞紦锛旓紩锛栵紬锛橈紮]+(\.[\d]+)+\s+(.+)"),
    re.compile(r"^\s*[銆怽[銆奭.+[銆慭]]\s*$"),
    re.compile(r"^\s{0,3}#{1,6}\s+(.+)"),
    # 鍥?1:  /  鍥?-1  (figure/table caption shortcut)
    re.compile(r"^\s*(?:\u56fe|\u8868|Figure|Fig\.?|Table)\s*" + _CAPTION_NUM_RE + r"(?:[\.:：、-]\s*|\s+)(.+)", re.IGNORECASE),
]

TABLE_ID_RE = re.compile(r"(?:\u8868|Table)\s*([\d]+(?:[._\uFF0E-][\da-zA-Z]+)*)", re.IGNORECASE)

# 娓呮礂閰嶇疆
MAX_CONSECUTIVE_BLANK_LINES: int = 2   # 瓒呰繃姝ゆ暟閲忓悎骞朵负涓€涓钀藉垎闅?MIN_LINE_CHARS: int = 2                 # 蹇界暐灏戜簬 N 瀛楃鐨?鍣煶"琛?

# ---------------------------------------------------------------------------
# Stage 1 鈥?Block extraction
# ---------------------------------------------------------------------------


def extract_blocks_from_page(page_num: int, blocks: list[dict[str, Any]]) -> list[PDFBlock]:
    """Convert pymupdf block list into typed PDFBlock list for one page.

    pymupdf ``page.get_text("dict")`` returns a list of block dicts each with
    ``type`` (0=text, 1=image, 2=math) and a ``lines`` sub-structure.
    We process only type-0 (text) blocks.
    """
    result: list[PDFBlock] = []

    for idx, block in enumerate(blocks):
        if block.get("type") != 0:        # skip images / math
            continue

        lines = block.get("lines", [])
        if not lines:
            continue

        raw_text = "\n".join(_block_lines_to_text(lines))
        if not raw_text.strip():
            continue

        block_type, heading_level = _classify_block(
            raw_text,
            lines,
            page_num=page_num,
            block_index=idx,
        )

        result.append(PDFBlock(
            block_type=block_type,
            text=raw_text,
            page=page_num,
            block_index=idx,
            heading_level=heading_level,
        ))

    return result


def _block_lines_to_text(lines: list[dict[str, Any]]) -> list[str]:
    """Flatten a pymupdf lines/spans structure into one line per row."""
    text_parts: list[str] = []
    for line in lines:
        spans = line.get("spans", [])
        line_text = "".join(span.get("text", "") for span in spans)
        if line_text:
            text_parts.append(line_text)
    return text_parts


def _caption_kind(text: str) -> str | None:
    stripped = text.strip()
    if _TABLE_CAPTION_START_RE.match(stripped):
        return "table"
    if _FIGURE_CAPTION_START_RE.match(stripped):
        return "figure"
    return None


def _is_page1_title_like(first_line: str, *, page_num: int | None, block_index: int | None) -> bool:
    if page_num != 1 or block_index is None or block_index > 2:
        return False

    stripped = first_line.strip()
    if not stripped or len(stripped) < 20 or len(stripped) > 220:
        return False
    if stripped.endswith((".", "\u3002", "?", "\uff1f", "!", "\uff01", ";", "\uff1b")):
        return False
    if _caption_kind(stripped) or _ABSTRACT_MARKER_RE.match(stripped) or _KEYWORDS_MARKER_RE.match(stripped):
        return False
    if any(token in stripped for token in ["University", "School", "Institute", "Laboratory", "@"]):
        return False

    words = re.findall(r"[A-Za-z][A-Za-z'-]*", stripped)
    if not (4 <= len(words) <= 24):
        return False

    stopwords = {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
        "of", "on", "or", "the", "to", "via", "with",
    }
    major_words = [word for word in words if word.lower() not in stopwords]
    if len(major_words) < 3:
        return False

    uppercase_ratio = sum(1 for word in major_words if word[0].isupper()) / max(len(major_words), 1)
    return uppercase_ratio >= 0.85


def _looks_like_multiline_allcaps_heading(raw_text: str) -> bool:
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    if not re.fullmatch(r"\d+", lines[0]):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z\s\-]{2,}", lines[1]))


def _looks_like_inferred_abstract_start(
    text: str,
    *,
    page_num: int,
    block_index: int,
    current_section: str,
    seen_page1_title: bool,
) -> bool:
    if page_num != 1 or not seen_page1_title or block_index > 8:
        return False

    stripped = text.strip()
    if len(stripped) < 80:
        return False
    if _caption_kind(stripped) or _ABSTRACT_MARKER_RE.match(stripped) or _KEYWORDS_MARKER_RE.match(stripped):
        return False
    if any(token in stripped for token in ["@", "University", "School", "Institute", "Laboratory"]):
        return False
    if _ALL_CAPS_SECTION_RE.match(stripped):
        return False

    words = re.findall(r"[A-Za-z][A-Za-z'-]*", stripped)
    return len(words) >= 12


def _classify_block(
    raw_text: str,
    lines: list[dict[str, Any]],
    *,
    page_num: int | None = None,
    block_index: int | None = None,
) -> tuple[BlockType, int]:
    """Return (BlockType, heading_level) for a text block."""

    # ---- Quick heuristics based on first line ----
    first_line = raw_text.strip().split("\n")[0].strip()

    # Skip pure page-number / header / footer artifacts
    if _looks_like_multiline_allcaps_heading(raw_text):
        return BlockType.HEADING, 1

    if _is_page_artifact(first_line, lines):
        return BlockType.OTHER, 0

    if _caption_kind(first_line):
        return BlockType.CAPTION, 0

    if _ALL_CAPS_SECTION_RE.match(first_line):
        return BlockType.HEADING, 1

    if _is_page1_title_like(first_line, page_num=page_num, block_index=block_index):
        return BlockType.HEADING, 1

    # ---- Heading patterns ----
    for pat in HEADING_PATTERNS:
        m = pat.match(first_line)
        if m:
            # Multi-level markdown heading
            if pat.pattern.startswith(r"^\s{0,3}#{1,6}"):
                level = len(first_line) - len(first_line.lstrip("#"))
                return BlockType.HEADING, min(level, 6)
            # Standalone caption like "鍥?1: 缁撴灉绀烘剰" or "琛?2-3"
            if _caption_kind(first_line):
                return BlockType.CAPTION, 0
            # Check for numbered list patterns BEFORE treating as heading
            # "1. item" is LIST_ITEM only if content after number is short (< 10 chars).
            # Longer content like "1. Introduction" is a heading, not a list item.
            li_match = re.match(r"^\s*[\d锛愶紤锛掞紦锛旓紩锛栵紬锛橈紮]+\.[\s銆€](.*)", first_line)
            if li_match and len(li_match.group(1).strip()) < 10:
                return BlockType.LIST_ITEM, 0

            return BlockType.HEADING, 1

    # ---- Section heading markers (Abstract / Keywords / 鎽樿) ----
    # These explicitly start a new section and should be treated as headings
    stripped_first = first_line.strip()
    if _ABSTRACT_MARKER_RE.match(stripped_first) or _KEYWORDS_MARKER_RE.match(stripped_first):
        return BlockType.HEADING, 1
    # Legacy explicit startswith checks are superseded by regex-based markers.

    # ---- Table detection ----
    import sys as _sys; _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if _looks_like_table(raw_text, lines):
        return BlockType.TABLE_LIKE, 0

    # ---- List detection ----
    if _looks_like_list(first_line):
        return BlockType.LIST_ITEM, 0

    # ---- Long text blocks default to paragraph ----
    # Relaxed: Chinese text often has short sentences/paragraphs.
    # ANY non-heading, non-table, non-list block is a candidate paragraph.
    # The accumulation logic in blocks_to_chunks handles merging.
    if len(raw_text) > 30:
        return BlockType.PARAGRAPH, 0

    # Short blocks with actual text content 鈫?paragraph (not "other")
    # "other" should only be page artifacts (page numbers, headers, footers)
    if len(raw_text.strip()) >= 2:
        return BlockType.PARAGRAPH, 0

    # Very short / empty 鈫?other
    return BlockType.OTHER, 0


def _is_page_artifact(first_line: str, lines: list[dict[str, Any]]) -> bool:
    """Detect headers, footers, page numbers."""
    stripped = first_line.strip()
    # Pure digit / roman numeral page numbers
    if re.fullmatch(r"[\divxlcdn]+\s*$", stripped) and len(stripped) < 6:
        return True
    # Common header/footer keywords
    if any(kw in stripped for kw in ["Copyright", "漏", "doi:", "arXiv", "ACM", "IEEE"]):
        return True
    return False


def _looks_like_table(raw_text: str, lines: list[dict[str, Any]]) -> bool:
    """Heuristic: a block that looks tabular (separator-rich, alignment).

    Require STRONG table evidence: multiple lines with actual column separators.
    A table row typically has 1+ column separator (鈹? |, :, tab).
    """
    # Must have minimum number of lines
    if len(lines) < TABLE_MIN_ROWS:
        return False

    # Count lines that ACTUALLY contain column separators
    separator_lines = 0
    for line in lines:
        spans = line.get("spans", [])
        line_text = "".join(span.get("text", "") for span in spans)
        # Count actual separators in the line
        sep_count = sum(1 for c in line_text if c in TABLE_COL_SEPARATOR_CHARS)
        if sep_count >= 1:
            separator_lines += 1

    if separator_lines < TABLE_MIN_ROWS:
        return False

    # Calculate ratio of separator-lines to total lines
    ratio = separator_lines / max(len(lines), 1)
    return ratio >= TABLE_LINE_RATIO


def _looks_like_list(first_line: str) -> bool:
    """Detect bullet / numbered list items."""
    stripped = first_line.strip()
    return bool(
        re.match(r"^[\-\*\+\u2022]\s+", stripped) or
        re.match(r"^\(?[\d]+\)?[\.、:]\s+", stripped) or
        re.match(r"^[a-z][\.\)]\s+", stripped.lower()) or   # "a." "b."
        re.match(r"^\([a-z]\)\s+", stripped, re.IGNORECASE) or  # "(a) item"
        re.match(r"^[\(]?[\u2460-\u2473]+[\.、\s]", stripped)
    )


# ---------------------------------------------------------------------------
# Stage 2 鈥?Block cleaning
# ---------------------------------------------------------------------------


def clean_block_text(text: str) -> str:
    """Basic text cleaning for a PDF block.

    - Normalize whitespace
    - Merge mid-sentence line breaks (common in Chinese PDFs)
    - Trim but preserve paragraph boundaries
    """
    # Replace various Unicode spaces with regular space
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    # Normalize newlines: normalize multiple blank lines
    lines = text.splitlines()
    # Filter out very short noise lines (single-char remnants)
    cleaned_lines: list[str] = []
    blank_run = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank_run += 1
            if blank_run <= MAX_CONSECUTIVE_BLANK_LINES:
                cleaned_lines.append("")
        else:
            blank_run = 0
            # Merge hyphenated line-endings: "word-\nnext" 鈫?"word-next"
            # Keep hyphen when merging (English hyphenation continuation)
            if (cleaned_lines and cleaned_lines[-1] and
                cleaned_lines[-1][-1] == "-"):
                cleaned_lines[-1] = cleaned_lines[-1][:-1] + "-" + stripped
            else:
                cleaned_lines.append(stripped)

    # Join with paragraph breaks
    result = "\n".join(cleaned_lines)
    # Collapse multiple spaces to one (but not newlines)
    result = re.sub(r" (?=\s)", " ", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Front matter heading split helpers
# ---------------------------------------------------------------------------

# Sentence-ending punctuation that marks end of first sentence
_SENTENCE_END_CHARS: frozenset = frozenset(".!?;。\uff01\uff1f\uff1b")


def _split_front_matter_heading(text: str) -> tuple[str, str] | None:
    """Check if a heading has the first abstract/body sentence merged in.

    For front matter headings (Abstract, 鎽?瑕? etc.), the PDF often merges
    the heading marker with the first sentence of the abstract body. This
    function detects that case and returns (heading_marker, body_text) so
    the caller can emit the marker as a heading chunk and feed the body
    into para_buf for natural accumulation.

    Returns (heading_marker, body_text) if split is needed, or None if not.
    """
    t = text.strip()
    match = _ABSTRACT_MARKER_RE.match(t)
    if not match:
        return None

    marker_part = t[: match.start(1)].strip()
    marker_part = marker_part.rstrip(":：").strip()
    body = (match.group(1) or "").strip()
    if len(body) < 10:
        return None

    for j, ch in enumerate(body):
        if ch in _SENTENCE_END_CHARS:
            return marker_part, body[:j + 1]
    return marker_part, body


# ---------------------------------------------------------------------------
# Stage 3 鈥?Block 鈫?Chunk conversion
# ---------------------------------------------------------------------------


def blocks_to_chunks(
    blocks: list[PDFBlock],
    *,
    doc_id: str,
    source: str,
    source_path: str,
    source_type: str,
    title: str,
    source_version: str,
    content_hash: str,
    last_ingested_at: str,
) -> list[tuple[str, ChunkMeta]]:
    """Convert typed PDF blocks into semantically coherent chunks.

    Strategy:
    1. Walk blocks top-to-bottom.
    2. HEADING  鈫?start a new section, emit as its own chunk if not too long.
    3. PARAGRAPH / LIST_ITEM 鈫?accumulate until near CHUNK_MAX_TOKENS,
       then flush and start new chunk. Merge short paragraphs.
    4. TABLE_LIKE 鈫?always emit as isolated chunk, do NOT merge with text.
    5. CAPTION 鈫?try to associate with preceding TABLE_LIKE, else emit alone.
    6. OTHER (non-artifact) 鈫?skip unless it bridges a gap.
    7. Oversized PARAGRAPH 鈫?sliding window fallback.

    Returns:
        List of (chunk_text, ChunkMeta) tuples.
    """

    chunks: list[tuple[str, ChunkMeta]] = []
    order = 0

    # ---- Pass 1: pre-process blocks ----
    cleaned: list[PDFBlock] = []
    for b in blocks:
        if not b.is_visible:
            continue
        ct = clean_block_text(b.text)
        if not ct:
            continue
        # Re-classify after cleaning (in case cleaning changed things)
        # For now keep the original type; we re-assign captions later
        cleaned.append(PDFBlock(
            block_type=b.block_type,
            text=ct,
            page=b.page,
            block_index=b.block_index,
            heading_level=b.heading_level,
        ))

    # ---- Helper: flush accumulated paragraph group ----
    para_buf: list[tuple[PDFBlock, str]] = []   # (block, cleaned_text)
    current_section = ""
    current_section_path: str | None = None   # hierarchical path like "1/1.2"
    current_semantic_type: str | None = None   # "abstract" for abstract-following paras
    current_table_id: str | None = None
    first_page = 0
    last_page = 0
    seen_page1_title = False
    prev_page = cleaned[0].page if cleaned else 0

    def _estimate_tokens(text: str) -> int:
        # Simple Chinese-aware token estimate: chars / 1.5 for CJK, words split by space
        words = re.findall(r"[\w\u4e00-\u9fff]+", text)
        cjk_chars = sum(len(w) for w in re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len([w for w in words if re.match(r"[\w]", w)])
        return int(cjk_chars / 1.5) + english_words

    def _flush_paragraphs() -> None:
        nonlocal chunks, order, para_buf, current_section, current_table_id, first_page, last_page
        if not para_buf:
            return

        combined = "\n".join(text for _, text in para_buf)
        tok = _estimate_tokens(combined)

        # Use 95% threshold to avoid edge cases where estimation is slightly off
        if tok <= int(CHUNK_MAX_TOKENS * 0.95):
            # Single chunk
            pages = [b.page for b, _ in para_buf]
            _emit_chunk(combined, BlockType.PARAGRAPH, min(pages), max(pages), current_table_id,
                        section_path=current_section_path, semantic_type=current_semantic_type)
        else:
            # Sliding window fallback - split by characters (approximate tokens)
            # Convert token size to approximate character size for Chinese
            char_size = int(CHUNK_MAX_TOKENS * 1.5)
            for sub in _sliding_window(combined, char_size, CHUNK_OVERLAP_TOKENS):
                pages = _pages_for_text(sub, para_buf)
                _emit_chunk(sub, BlockType.PARAGRAPH, min(pages), max(pages), current_table_id,
                            section_path=current_section_path, semantic_type=current_semantic_type)

        para_buf.clear()
        current_table_id = None

    def _emit_chunk(
        text: str,
        btype: BlockType,
        p_start: int,
        p_end: int,
        table_id: str | None,
        section_path: str | None = None,
        semantic_type: str | None = None,
    ) -> None:
        nonlocal chunks, order
        nonlocal current_section, current_section_path, current_semantic_type, current_table_id, first_page, last_page, seen_page1_title
        if not text.strip():
            return
        tok = _estimate_tokens(text)
        chunk_id = f"{doc_id}:{order}"
        location = f"page {p_start}" if p_start == p_end else f"pages {p_start}-{p_end}"
        ref = f"{title} > {current_section}" if current_section else f"{title} > page {p_start}"
        meta = ChunkMeta(
            doc_id=doc_id,
            chunk_id=chunk_id,
            source=source,
            source_path=source_path,
            source_type=source_type,
            title=title,
            block_type=btype.value,
            section_title=current_section,
            table_id=table_id,
            page_start=p_start,
            page_end=p_end,
            order_in_doc=order,
            char_count=len(text),
            token_estimate=tok,
            location=location,
            ref=ref,
            source_version=source_version,
            content_hash=content_hash,
            last_ingested_at=last_ingested_at,
            ingest_status="ready",
            section_path=section_path if section_path is not None else current_section_path,
            semantic_type=semantic_type if semantic_type is not None else current_semantic_type,
        )
        chunks.append((text, meta))
        if btype == BlockType.HEADING and p_start == 1 and _is_page1_title_like(text, page_num=1, block_index=0):
            seen_page1_title = True
        order += 1

    def _pages_for_text(sub: str, buf: list[tuple[PDFBlock, str]]) -> list[int]:
        pages: list[int] = []
        for b, t in buf:
            if t in sub or sub in t:
                pages.append(b.page)
        return pages or [buf[0][0].page] if buf else [1]

    def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
        """Character-level sliding window for oversized paragraphs."""
        step = max(1, size - overlap)
        windows: list[str] = []
        for start in range(0, len(text), step):
            w = text[start: start + size].strip()
            if w:
                windows.append(w)
            if start + size >= len(text):
                break
        return windows

    i = 0
    while i < len(cleaned):
        b = cleaned[i]

        # Update current section (heading tracking)
        if b.block_type == BlockType.HEADING:
            # Flush accumulated paragraphs when heading appears on a new page —
            # prevents multi-page headings from incorrectly merging with
            # previous page content into a single chunk.
            heading_page_change = b.page != prev_page
            if heading_page_change and para_buf:
                _flush_paragraphs()
            _flush_paragraphs()

            # Front matter headings (Abstract / 摘要 often have the first sentence
            # merged into the same PDF block. Split them: emit heading marker as HEADING,
            # body content 鈫?paragraph buffer for natural accumulation with subsequent blocks.
            result = _split_front_matter_heading(b.text)
            if result is not None:
                heading_marker, body_text = result
                # Normalize: replace ideographic spaces with regular spaces for consistency
                normalized_marker = heading_marker.replace("\u3000", " ").strip()
                _emit_chunk(normalized_marker, BlockType.HEADING, b.page, b.page, None)
                # Track this as the current section so subsequent body paragraphs
                # (which will be added to para_buf below) inherit the section title
                current_section = normalized_marker
                # Mark subsequent paragraphs as abstract section
                current_semantic_type = "abstract"
                # Put body content into para_buf so it merges with following abstract paragraphs
                buf_block = PDFBlock(
                    block_type=BlockType.PARAGRAPH,
                    text=body_text,
                    page=b.page,
                    block_index=b.block_index,
                    heading_level=0,
                )
                para_buf.append((buf_block, body_text))
                prev_page = b.page
                i += 1
                continue

            # Clean heading text for section title - strip markdown prefix and extra chars
            heading_text = b.text[:MAX_HEADING_CHARS].strip()
            # Track hierarchical section path BEFORE stripping the number prefix
            num_match = re.match(r"^([\d]+(?:\.[\d]+)*)\s+(.+)$", b.text.strip())
            if num_match:
                num_prefix = num_match.group(1)
                level = num_prefix.count(".") + 1
                # Build path components from the number prefix
                parts = num_prefix.split(".")
                path_parts = []
                for idx, part in enumerate(parts):
                    if idx == 0:
                        path_parts.append(part)
                    else:
                        path_parts.append(f"{parts[idx-1]}.{part}")
                current_section_path = "/".join(path_parts)

            # Remove common heading prefixes
            heading_text = re.sub(r"^#{1,6}\s+", "", heading_text)  # markdown #
            # Explicitly strip "digit+newline" prefix from multiline headings (e.g. "1\nINTRODUCTION")
            heading_text = re.sub(r"^\d+\n", "", heading_text)
            heading_text = re.sub(r"^[\d０１２３４５６７８９]+(\.[\d]+)*[．.、\s]+", "", heading_text)  # numbered headings
            heading_text = re.sub(r"^[銆怽[銆奭.+[銆慭]]\s*$", "", heading_text)  # bracketed titles
            current_section = heading_text.strip()
            # Reset semantic type when exiting front matter (any non-abstract heading)
            current_semantic_type = None

            if _is_page1_title_like(b.text, page_num=b.page, block_index=b.block_index):
                seen_page1_title = True

            # Emit heading as its own chunk if reasonably short.
            # If heading is on a new page and we flushed para_buf, do NOT add to para_buf
            # (it was already emitted above); just advance.
            tok = _estimate_tokens(b.text)
            if tok <= CHUNK_MAX_TOKENS:
                if not (heading_page_change and para_buf):
                    # Normal case: heading fits, emit it directly
                    _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
            else:
                # Heading too long 鈫?treat as paragraph, add to para_buf
                para_buf.append((b, b.text))
            prev_page = b.page
            i += 1
            continue

        # TABLE_LIKE: always isolate
        if b.block_type == BlockType.TABLE_LIKE:
            _flush_paragraphs()
            # Try to extract table number from surrounding caption blocks
            table_id = _extract_table_id_from_block(b)
            _emit_chunk(b.text, BlockType.TABLE_LIKE, b.page, b.page, table_id)
            prev_page = b.page
            i += 1
            continue

        # CAPTION: try to merge with preceding table
        if b.block_type == BlockType.CAPTION:
            table_id = _extract_table_id(b.text)
            if (
                chunks
                and chunks[-1][1].block_type == BlockType.TABLE_LIKE.value
                and table_id
                and chunks[-1][1].table_id is None
            ):
                # Retroactively attach caption's table_id to previous table chunk
                old_text, old_meta = chunks[-1]
                updated_meta = ChunkMeta(
                    **{
                        **old_meta.__dict__,
                        "table_id": table_id,
                        "ref": f"{title} > {table_id}",
                    }
                )
                chunks[-1] = (old_text, updated_meta)
                # Also append caption text to table chunk
                combined = old_text + "\n" + b.text
                updated_meta2 = ChunkMeta(
                    **{
                        **updated_meta.__dict__,
                        "char_count": len(combined),
                        "token_estimate": _estimate_tokens(combined),
                    }
                )
                chunks[-1] = (combined, updated_meta2)
            else:
                # Standalone caption
                _emit_chunk(b.text, BlockType.CAPTION, b.page, b.page, table_id)
            prev_page = b.page
            i += 1
            continue

        # LIST_ITEM: accumulate like paragraph
        if b.block_type == BlockType.LIST_ITEM:
            para_buf.append((b, b.text))
            i += 1
            prev_page = b.page
            continue

        # PARAGRAPH (default)
        if b.block_type == BlockType.PARAGRAPH or b.block_type == BlockType.OTHER:
            # Flush paragraph buffer when page changes — prevents multi-page paragraphs
            # from being incorrectly merged into a single chunk.
            page_change = b.page != prev_page
            if page_change and para_buf:
                _flush_paragraphs()

            # Chinese title detection: emit immediately as heading (no markdown marker in PDF).
            # Pure Chinese, no sentence-ending punctuation, first block on page 1.
            if para_buf == [] and b.page == 1:
                stripped = b.text.strip()
                has_chinese = any("\u4e00" <= c <= "\u9fff" for c in stripped)
                has_ascii_letter = any(c.isalpha() and c.isascii() for c in stripped)
                has_end_punct = stripped.endswith(("\u3002", "\uff1f", "\uff01", "?", "!"))
                is_short = len(stripped) < 8
                # Author/affiliation markers: digit-comma patterns, "澶у", "瀛﹂櫌", emails
                has_author_marker = (
                    re.search(r"\d+\s*[,，]\s*\d*", stripped) is not None
                    or "大学" in stripped
                    or "学院" in stripped
                    or "研究生院" in stripped
                    or "@" in stripped
                    or re.match(r"^\s*[\d\u3000\u00a0]+", stripped) is not None
                )
                if has_chinese and not has_ascii_letter and not has_end_punct and not is_short and not has_author_marker:
                    _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
                    prev_page = b.page
                    i += 1
                    continue

            # Anchor-based flush: front matter boundaries force a flush.
            # These section keywords mark the end of front matter or transitions.
            # Uses re.IGNORECASE for English keywords and char-level spans for Chinese.
            ANCHOR_PATTERNS: list[tuple[str, bool]] = [
                (r"abstract\b", True),
                (r"key words\b", True),
                (r"^[\s\u3000]*摘\s*要", False),
                (r"^[\s\u3000]*关键词", False),
                (r"^[\s\u3000]*中图法分类号", False),
                (r"^[\s\u3000]*基金项目", False),
                (r"^[\s\u3000]*作者简介", False),
                (r"^[\s\u3000]*收稿日期", False),
                (r"^[\s\u3000]*修回日期", False),
                (r"^[\s\u3000]*通信作者", False),
            ]
            stripped_lower = b.text.strip().lower()
            is_anchor_block = False
            for pat, is_english in ANCHOR_PATTERNS:
                if is_english:
                    if re.search(pat, stripped_lower, re.IGNORECASE):
                        is_anchor_block = True
                        break
                else:
                    if re.match(pat, stripped_lower):
                        is_anchor_block = True
                        break
            if is_anchor_block and para_buf:
                _flush_paragraphs()
            if is_anchor_block:
                _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
                prev_page = b.page
                i += 1
                continue
            is_inferred_abstract_start = _looks_like_inferred_abstract_start(
                b.text,
                page_num=b.page,
                block_index=b.block_index,
                current_section=current_section,
                seen_page1_title=seen_page1_title,
            )
            if is_inferred_abstract_start and para_buf:
                _flush_paragraphs()
            if is_inferred_abstract_start:
                current_section = "Abstract"
            para_buf.append((b, b.text))
            prev_page = b.page
            i += 1
            continue

        i += 1

    # Flush any remaining paragraphs
    _flush_paragraphs()

    return chunks


def _extract_table_id_from_block(block: PDFBlock) -> str | None:
    """Try to find a table ID in the block text itself."""
    return _extract_table_id(block.text)


def _extract_table_id(text: str) -> str | None:
    m = TABLE_ID_RE.search(text)
    if m:
        return f"Table {m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# Top-level entry point used by source_loader / ingest
# ---------------------------------------------------------------------------


def structured_pdf_chunks(
    pages: list[dict[str, Any]],   # list of {page: int, blocks: list}
    *,
    doc_id: str,
    source: str,
    source_path: str,
    source_type: str,
    title: str,
    source_version: str,
    content_hash: str,
    last_ingested_at: str,
) -> list[tuple[str, ChunkMeta]]:
    """High-level API: structured PDF block extraction + chunking.

    Args:
        pages: List of dicts with keys ``page`` (1-based int) and ``blocks``
              (list of pymupdf block dicts as returned by ``page.get_text("dict")``).

    Returns:
        List of (chunk_text, ChunkMeta) tuples ready for Document construction.
    """
    all_blocks: list[PDFBlock] = []
    for page_data in pages:
        page_num = page_data["page"]
        page_blocks = page_data.get("blocks", [])
        all_blocks.extend(extract_blocks_from_page(page_num, page_blocks))

    return blocks_to_chunks(
        all_blocks,
        doc_id=doc_id,
        source=source,
        source_path=source_path,
        source_type=source_type,
        title=title,
        source_version=source_version,
        content_hash=content_hash,
        last_ingested_at=last_ingested_at,
    )
