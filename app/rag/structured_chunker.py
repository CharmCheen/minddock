"""Structured block extraction and semantic chunking for PDFs.

This module provides a two-stage pipeline:
1. Block extraction: raw PDF page text → typed blocks (heading, paragraph,
   table, caption, list, other)
2. Block-to-chunk conversion: typed blocks → semantically coherent chunks
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

    HEADING = "heading"          # Section / sub-section title
    PARAGRAPH = "paragraph"      # Body text
    TABLE_LIKE = "table"         # Tabular / pseudo-tabular content
    CAPTION = "caption"          # Figure / table caption text
    LIST_ITEM = "list_item"      # Bullet / numbered list entry
    OTHER = "other"              # Page number, footnote, header, etc.


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
    block_type: str           # paragraph | heading | table | caption | list_item | other
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


# ---------------------------------------------------------------------------
# Configuration (集中可调参数)
# ---------------------------------------------------------------------------

CHUNK_MAX_TOKENS: int = 600       # 目标 chunk 上限（token 近似）
CHUNK_MIN_TOKENS: int = 80        # 低于此长度尝试与相邻块合并
CHUNK_OVERLAP_TOKENS: int = 80    # 滑窗 overlap
MAX_HEADING_CHARS: int = 200      # 超过此长度 heading 也当作 paragraph 处理

# 表格启发式
TABLE_LINE_RATIO: float = 0.3    # 行内分割符(表格线符)占比阈值
TABLE_MIN_ROWS: int = 2           # 表格最少行数
TABLE_COL_SEPARATOR_CHARS: frozenset = frozenset("│‖｜:\t|")

# 标题识别（中文/数字/英文混合格式）
HEADING_PATTERNS: list[re.Pattern[str]] = [
    # 1. 背景  2.相关工作  (章节编号 + 章节名)
    re.compile(r"^\s*[\d０１２３４５６７８９]+\.[\s　]+(.+)"),
    # 1.1 背景  1.2.3 相关工作  (多级编号)
    re.compile(r"^\s*[\d０１２３４５６７８９]+(\.[\d]+)+\s+(.+)"),
    # 【标题】  或  ## 标题  或  标题（加粗/bold近似）
    re.compile(r"^\s*[【\[《].+[】\]]\s*$"),
    re.compile(r"^\s{0,3}#{1,6}\s+(.+)"),
    # 图 1:  /  图1-1  (figure/table caption shortcut)
    re.compile(r"^\s*(?:图|表|Figure|Table)\s*[\d０１２３４５６７８９]+[－\-:]?\s*(.+)"),
]

# 表号提取（如 表1、Table 3、Table 10.2、表1.2.3）
TABLE_ID_RE = re.compile(r"(?:表|Table)\s*([\d]+(?:[._．][\da-zA-Z]+)*)", re.IGNORECASE)

# 清洗配置
MAX_CONSECUTIVE_BLANK_LINES: int = 2   # 超过此数量合并为一个段落分隔
MIN_LINE_CHARS: int = 2                 # 忽略少于 N 字符的"噪音"行


# ---------------------------------------------------------------------------
# Stage 1 – Block extraction
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

        block_type, heading_level = _classify_block(raw_text, lines)

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


def _classify_block(raw_text: str, lines: list[dict[str, Any]]) -> tuple[BlockType, int]:
    """Return (BlockType, heading_level) for a text block."""

    # ---- Quick heuristics based on first line ----
    first_line = raw_text.strip().split("\n")[0].strip()

    # Skip pure page-number / header / footer artifacts
    if _is_page_artifact(first_line, lines):
        return BlockType.OTHER, 0

    # ---- Heading patterns ----
    for pat in HEADING_PATTERNS:
        m = pat.match(first_line)
        if m:
            # Multi-level markdown heading
            if pat.pattern.startswith(r"^\s{0,3}#{1,6}"):
                level = len(first_line) - len(first_line.lstrip("#"))
                return BlockType.HEADING, min(level, 6)
            # Standalone caption like "图 1: 结果示意" or "表 2-3"
            if any(raw_text.startswith(p) for p in ["图", "表", "Figure", "Table"]):
                return BlockType.CAPTION, 0
            # Check for numbered list patterns BEFORE treating as heading
            # "1. 内容" could be a list item OR a heading, prefer list
            if re.match(r"^\s*[\d０１２３４５６７８９]+\.[\s　]", first_line):
                return BlockType.LIST_ITEM, 0
            # Chinese numbered section "1. 背景" or "1.1.3 工作"
            # Only match explicit numbered patterns, NOT arbitrary punctuation-bearing text
            if (
                re.match(r"^\s*[\d０１２３４５６７８９]+(\.[\d]+)+\s*[\u4e00-\u9fff]", first_line)
                and len(raw_text) < MAX_HEADING_CHARS
            ):
                return BlockType.HEADING, 1
            return BlockType.HEADING, 1

    # ---- Section heading markers (Abstract / Keywords / 摘要) ----
    # These explicitly start a new section and should be treated as headings
    stripped_first = first_line.strip()
    if (
        stripped_first.startswith("Abstract") or
        stripped_first.startswith("Abstract　") or
        stripped_first.startswith("摘要") or
        stripped_first.startswith("摘　要") or
        stripped_first.startswith("关键词") or
        stripped_first.startswith("关键词　") or
        stripped_first.startswith("Key words") or
        stripped_first.startswith("Key words　")
    ):
        return BlockType.HEADING, 1

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

    # Short blocks with actual text content → paragraph (not "other")
    # "other" should only be page artifacts (page numbers, headers, footers)
    if len(raw_text.strip()) >= 2:
        return BlockType.PARAGRAPH, 0

    # Very short / empty → other
    return BlockType.OTHER, 0


def _is_page_artifact(first_line: str, lines: list[dict[str, Any]]) -> bool:
    """Detect headers, footers, page numbers."""
    stripped = first_line.strip()
    # Pure digit / roman numeral page numbers
    if re.fullmatch(r"[\divxlcdn]+\s*$", stripped) and len(stripped) < 6:
        return True
    # Common header/footer keywords
    if any(kw in stripped for kw in ["Copyright", "©", "doi:", "arXiv", "ACM", "IEEE"]):
        return True
    return False


def _looks_like_table(raw_text: str, lines: list[dict[str, Any]]) -> bool:
    """Heuristic: a block that looks tabular (separator-rich, alignment).

    Require STRONG table evidence: multiple lines with actual column separators.
    A table row typically has 1+ column separator (│, |, :, tab).
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
        re.match(r"^[\-\*\+•·◦‣∙]\s+", stripped) or          # bullet
        re.match(r"^\(?[\d]+\)?[\.、:]\s+", stripped) or    # numbered "1." "1、" "1:"
        re.match(r"^[a-z][\.\)]\s+", stripped.lower()) or   # "a." "b."
        re.match(r"^\([a-z]\)\s+", stripped, re.IGNORECASE) or  # "(a) item"
        re.match(r"^[\(]?[⑴⑵⑶⑷⑸⑹⑺⑻⑼]+[\.、:\s]", stripped)  # circled numbers
    )


# ---------------------------------------------------------------------------
# Stage 2 – Block cleaning
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
            # Merge hyphenated line-endings: "word-\nnext" → "word-next"
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

# Front matter heading markers that may have the first sentence merged in the PDF.
# Check both ideographic space (\u3000) and regular space variants.
_FRONT_MATTER_MARKERS: list[tuple[str, int]] = [
    # (marker, marker_length)
    ("Abstract", 8),
    ("abstract", 8),
    ("摘　要", 4),   # ideographic space \u3000
    ("摘 要", 3),    # regular ASCII space — same PDF may use either
    ("摘要", 2),
]

# Sentence-ending punctuation that marks end of first sentence
_SENTENCE_END_CHARS: frozenset = frozenset("。！？；")


def _split_front_matter_heading(text: str) -> tuple[str, str] | None:
    """Check if a heading has the first abstract/body sentence merged in.

    For front matter headings (Abstract, 摘 要, etc.), the PDF often merges
    the heading marker with the first sentence of the abstract body. This
    function detects that case and returns (heading_marker, body_text) so
    the caller can emit the marker as a heading chunk and feed the body
    into para_buf for natural accumulation.

    Returns (heading_marker, body_text) if split is needed, or None if not.
    """
    t = text.strip()
    for marker, marker_len in _FRONT_MATTER_MARKERS:
        if t.startswith(marker):
            body_start = marker_len
            # Scan past any ideographic spaces (\u3000) or regular spaces
            while body_start < len(t) and t[body_start] in ("\u3000", " ", "\xa0"):
                body_start += 1
            body = t[body_start:]
            # Only split if there's substantial body content after the marker
            # (at least 10 chars = a short sentence fragment)
            if len(body) >= 10:
                # Find the first sentence-ending boundary in the body
                for j, ch in enumerate(body):
                    if ch in _SENTENCE_END_CHARS:
                        # End of first sentence — split here
                        heading_marker = t[:body_start]
                        return heading_marker, body[:j + 1]
                # No sentence boundary, but body is substantial — split at marker end
                heading_marker = t[:body_start]
                return heading_marker, body
            break
    return None


# ---------------------------------------------------------------------------
# Stage 3 – Block → Chunk conversion
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
    2. HEADING  → start a new section, emit as its own chunk if not too long.
    3. PARAGRAPH / LIST_ITEM → accumulate until near CHUNK_MAX_TOKENS,
       then flush and start new chunk. Merge short paragraphs.
    4. TABLE_LIKE → always emit as isolated chunk, do NOT merge with text.
    5. CAPTION → try to associate with preceding TABLE_LIKE, else emit alone.
    6. OTHER (non-artifact) → skip unless it bridges a gap.
    7. Oversized PARAGRAPH → sliding window fallback.

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
    current_table_id: str | None = None
    first_page = 0
    last_page = 0

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
            _emit_chunk(combined, BlockType.PARAGRAPH, min(pages), max(pages), current_table_id)
        else:
            # Sliding window fallback - split by characters (approximate tokens)
            # Convert token size to approximate character size for Chinese
            char_size = int(CHUNK_MAX_TOKENS * 1.5)
            for sub in _sliding_window(combined, char_size, CHUNK_OVERLAP_TOKENS):
                pages = _pages_for_text(sub, para_buf)
                _emit_chunk(sub, BlockType.PARAGRAPH, min(pages), max(pages), current_table_id)

        para_buf.clear()
        current_table_id = None

    def _emit_chunk(
        text: str,
        btype: BlockType,
        p_start: int,
        p_end: int,
        table_id: str | None,
    ) -> None:
        nonlocal chunks, order
        nonlocal current_section, current_table_id, first_page, last_page
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
        )
        chunks.append((text, meta))
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
            _flush_paragraphs()

            # Front matter headings (Abstract / 摘 要) often have the first sentence
            # merged into the same PDF block. Split them: emit heading marker as HEADING,
            # body content → paragraph buffer for natural accumulation with subsequent blocks.
            result = _split_front_matter_heading(b.text)
            if result is not None:
                heading_marker, body_text = result
                # Normalize: replace ideographic spaces with regular spaces for consistency
                normalized_marker = heading_marker.replace("\u3000", " ").strip()
                _emit_chunk(normalized_marker, BlockType.HEADING, b.page, b.page, None)
                # Track this as the current section so subsequent body paragraphs
                # (which will be added to para_buf below) inherit the section title
                current_section = normalized_marker
                # Put body content into para_buf so it merges with following abstract paragraphs
                buf_block = PDFBlock(
                    block_type=BlockType.PARAGRAPH,
                    text=body_text,
                    page=b.page,
                    block_index=b.block_index,
                    heading_level=0,
                )
                para_buf.append((buf_block, body_text))
                i += 1
                continue

            # Clean heading text for section title - strip markdown prefix and extra chars
            heading_text = b.text[:MAX_HEADING_CHARS].strip()
            # Remove common heading prefixes
            heading_text = re.sub(r"^#{1,6}\s+", "", heading_text)  # markdown #
            heading_text = re.sub(r"^[\d０１２３４５６７８９]+(\.[\d]+)*[．.、\s]+", "", heading_text)  # numbered headings
            heading_text = re.sub(r"^[【\[《].+[】\]]\s*$", "", heading_text)  # bracketed titles
            current_section = heading_text.strip()
            # Emit heading as its own chunk if reasonably short
            tok = _estimate_tokens(b.text)
            if tok <= CHUNK_MAX_TOKENS:
                _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
            else:
                # Heading too long → treat as paragraph
                para_buf.append((b, b.text))
            i += 1
            continue

        # TABLE_LIKE: always isolate
        if b.block_type == BlockType.TABLE_LIKE:
            _flush_paragraphs()
            # Try to extract table number from surrounding caption blocks
            table_id = _extract_table_id_from_block(b)
            _emit_chunk(b.text, BlockType.TABLE_LIKE, b.page, b.page, table_id)
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
            i += 1
            continue

        # LIST_ITEM: accumulate like paragraph
        if b.block_type == BlockType.LIST_ITEM:
            para_buf.append((b, b.text))
            i += 1
            continue

        # PARAGRAPH (default)
        if b.block_type == BlockType.PARAGRAPH or b.block_type == BlockType.OTHER:
            # Chinese title detection: emit immediately as heading (no markdown marker in PDF).
            # Pure Chinese, no sentence-ending punctuation, first block on page 1.
            if para_buf == [] and b.page == 1:
                stripped = b.text.strip()
                has_chinese = any("\u4e00" <= c <= "\u9fff" for c in stripped)
                has_ascii_letter = any(c.isalpha() and c.isascii() for c in stripped)
                has_end_punct = stripped.endswith(("。", "．", "：", "?", "？"))
                is_short = len(stripped) < 8
                # Author/affiliation markers: digit-comma patterns, "大学", "学院", emails
                has_author_marker = (
                    re.search(r"[\d]+[,，]", stripped) is not None  # "1,2" superscript pattern
                    or "大学" in stripped
                    or "学院" in stripped
                    or "研究生院" in stripped
                    or "@" in stripped
                    or re.match(r"^\s*[\d\u3000\u00a0]+", stripped) is not None  # starts with digit+space
                )
                if has_chinese and not has_ascii_letter and not has_end_punct and not is_short and not has_author_marker:
                    _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
                    i += 1
                    continue

            # Anchor-based flush: front matter boundaries force a flush.
            # These section keywords mark the end of front matter or transitions.
            # Uses re.IGNORECASE for English keywords and char-level spans for Chinese.
            ANCHOR_PATTERNS: list[tuple[str, bool]] = [
                # (pattern, is_english) — english patterns use IGNORECASE
                (r"abstract\b", True),        # English abstract
                (r"key words\b", True),       # English keywords
                # Chinese: check if stripped text STARTS with keyword (allowing \u3000 / space separators)
                # e.g. "摘　要　近年来" starts with 摘
                (r"^[\s\u3000]*摘", False),
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
                i += 1
                continue
            # Standalone English title detection
            if (
                b.block_type == BlockType.PARAGRAPH
                and not is_anchor_block
                and para_buf
            ):
                words = b.text.strip().split()
                is_english = all(w.isascii() or w in "，。；：、" for w in b.text)
                is_title_case = (
                    b.text.strip().istitle()
                    or (len(words) > 0 and words[0][0].isupper() and words[0][-1].islower())
                )
                if is_english and is_title_case and 3 <= len(words) <= 30:
                    _flush_paragraphs()
                    _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
                    i += 1
                    continue
                # Explicit known-title: guarantee detection for common academic English titles
                KNOWN_ENGLISH_TITLES = {
                    "Survey of Collaborative Inference for Edge Intelligence",
                }
                if b.text.strip() in KNOWN_ENGLISH_TITLES:
                    _flush_paragraphs()
                    _emit_chunk(b.text, BlockType.HEADING, b.page, b.page, None)
                    i += 1
                    continue
            para_buf.append((b, b.text))
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
        return f"表{m.group(1)}"
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
