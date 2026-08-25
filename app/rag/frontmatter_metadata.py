"""Academic front-matter metadata extraction at ingest time (PRD FR-3).

Extracts conservative, deterministic ``doc_authors`` and ``doc_year`` hints
from the head of a document so that later retrieval can filter by author or
publication year. Heuristics are deliberately cautious: when nothing matches,
fields are omitted rather than guessed. Only text-like sources (pdf / md /
txt) are eligible; media transcripts, OCR output, and CSV rows-as-text are
excluded by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCAN_CHARS = 3000
_YEAR_SCAN_CHARS = 1500
_MAX_AUTHOR_LINES = 40
_MAX_AUTHORS = 8

_YEAR_RE = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")
_EN_NAME_RE = re.compile(r"\b[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,3}\b")
_CN_NAME_RE = re.compile(r"[\u4e00-\u9fa5]{2,4}")
_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")

# Lines matching any of these are structural/affiliation/backmatter noise.
_AUTHOR_LINE_BLACKLIST = re.compile(
    r"(university|institute|department|laborator|college|school of|academy"
    r"|journal|transactions|vol\.|volume|issue|no\.|pp\.|pages|proceedings"
    r"|doi|issn|isbn|arxiv|abstract|keywords|©|copyright|licensed"
    r"|corresponding|e-?mail|@|http|www\.|received|accepted|revised|published"
    r"|editor|reviewer|conference|symposium|press|publisher"
    r"|中图分类|收稿|基金|摘要|关键词|大学|研究所|实验室|学报|出版社)",
    re.IGNORECASE,
)

# English words that match the capitalized-name pattern but never are names.
_NAME_STOPWORDS = frozenset(
    {
        "the",
        "this",
        "that",
        "these",
        "those",
        "we",
        "our",
        "in",
        "on",
        "for",
        "and",
        "with",
        "from",
        "page",
        "figure",
        "table",
        "chapter",
        "section",
        "abstract",
        "keywords",
        "introduction",
        "related",
        "conclusion",
        "references",
        "proposed",
        "based",
        "using",
        "towards",
        "toward",
    }
)

_SEPARATORS_RE = re.compile(r"[,，;；、]|和|与|\band\b", re.IGNORECASE)


@dataclass(frozen=True)
class AcademicDocMetadata:
    """Extracted academic hints for one document."""

    authors: str | None = None
    year: int | None = None
    extraction: str = "rule_v1"

    def to_metadata_pairs(self) -> dict[str, object]:
        pairs: dict[str, object] = {}
        if self.authors:
            pairs["doc_authors"] = self.authors
        if self.year is not None:
            pairs["doc_year"] = self.year
        return pairs


def is_academic_metadata_eligible(*, source_type: str, loader_name: str | None) -> bool:
    """Only text-like document sources get academic metadata extraction."""

    if str(source_type or "").strip().lower() != "file":
        return False
    normalized_loader = str(loader_name or "").strip().lower()
    excluded = {"csv", "image.ocr", "audio.transcribe", "video.transcribe"}
    return normalized_loader not in excluded


def extract_academic_metadata(text: str, *, title_hint: str | None = None) -> AcademicDocMetadata:
    """Extract (authors, year) hints from the head of one document."""

    head = str(text or "")[:_SCAN_CHARS]
    if not head.strip():
        return AcademicDocMetadata()

    year = _extract_year(head)
    authors = _extract_authors(head, title_hint=title_hint)
    return AcademicDocMetadata(authors=authors, year=year)


def _extract_year(head: str) -> int | None:
    match = _YEAR_RE.search(head[:_YEAR_SCAN_CHARS])
    if match is None:
        return None
    return int(match.group(1))


def _extract_authors(head: str, *, title_hint: str | None) -> str | None:
    cjk_density = len(_CJK_RE.findall(head)) / max(1, len(head))
    use_chinese = cjk_density > 0.25

    lines = head.splitlines()[:_MAX_AUTHOR_LINES]
    title_line = str(title_hint or "").strip().lower()
    collected: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if title_line and stripped.lower() == title_line:
            continue
        # Stop at the abstract/body boundary: everything after belongs to content.
        if re.search(r"^(abstract|keywords|introduction|摘要|关键词)", stripped, re.IGNORECASE):
            break
        if _AUTHOR_LINE_BLACKLIST.search(stripped):
            continue
        if len(stripped) > 120 or len(stripped) < 4:
            continue
        names = _names_from_line(stripped, use_chinese=use_chinese)
        for name in names:
            if name.lower() in _NAME_STOPWORDS:
                continue
            if name not in collected:
                collected.append(name)
        if len(collected) >= _MAX_AUTHORS:
            break

    if not collected:
        return None
    return "; ".join(collected[:_MAX_AUTHORS])


def _names_from_line(line: str, *, use_chinese: bool) -> list[str]:
    if use_chinese:
        parts = [part.strip() for part in _SEPARATORS_RE.split(line) if part.strip()]
        names: list[str] = []
        for part in parts:
            cleaned = part.strip("·•-— ")
            if 2 <= len(cleaned) <= 4 and _CJK_RE.search(cleaned):
                names.append(cleaned)
        return names

    candidates = _EN_NAME_RE.findall(line)
    filtered = []
    for candidate in candidates:
        words = candidate.split()
        # Real personal names have 2+ capitalized tokens; drop single tokens
        # and sentences that slipped through (contain lowercase connectors).
        if len(words) < 2:
            continue
        if any(word.lower() in _NAME_STOPWORDS for word in words):
            continue
        filtered.append(candidate)
    return filtered
