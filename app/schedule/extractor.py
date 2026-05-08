"""Rule-based schedule candidate extractor.

Extracts dates, times, and event keywords from text chunks to produce
ScheduleCandidate objects. No LLM involvement — pure regex + keyword matching.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.schedule.models import ScheduleCandidate

# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

SCHEDULE_KEYWORDS: tuple[str, ...] = (
    # Chinese
    "答辩", "会议", "截止", "提交", "考试", "面试", "上课", "课程",
    "讨论", "演示", "汇报", "开题", "中期", "终期", "研讨",
    "注册", "选课", "缴费", "体检", "报到",
    # English
    "deadline", "meeting", "exam", "interview", "submit",
    "presentation", "workshop", "seminar", "conference",
)

_KEYWORDS_LOWER = tuple(kw.lower() for kw in SCHEDULE_KEYWORDS)

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

# ISO: 2026-05-20
_DATE_ISO = re.compile(r"\b(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")

# Slash: 2026/05/20
_DATE_SLASH = re.compile(r"\b(\d{4})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])\b")

# Chinese full: 2026年5月20日
_DATE_CN_FULL = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})[日号]")

# Chinese month-day: 5月20日 (no year)
_DATE_CN_MD = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]")

# English: May 20, 2026 / May 20 2026
_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DATE_EN = re.compile(
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)

# Weekday (Chinese)
_WEEKDAY_CN = re.compile(r"(?:周|星期)(一|二|三|四|五|六|日|天)")

# ---------------------------------------------------------------------------
# Time patterns
# ---------------------------------------------------------------------------

# Chinese time: 上午9点 / 下午2点30分 / 晚上8点半
_TIME_CN = re.compile(
    r"(上午|下午|早上|晚上|中午|凌晨)?\s*(\d{1,2})[点时:：](\d{1,2})?[分]?"
)

# 24h: 14:30
_TIME_24H = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")

# Time range with dash: 9:00-11:00 / 14:30~16:00
_TIME_RANGE = re.compile(
    r"\b(\d{1,2}:\d{2})\s*[-~—至到]\s*(\d{1,2}:\d{2})\b",
)

# Chinese time range: 上午9点-11点
_TIME_CN_RANGE = re.compile(
    r"(上午|下午|早上|晚上|中午|凌晨)?\s*(\d{1,2})[点时]\s*[-~—至到]\s*(上午|下午|早上|晚上|中午|凌晨)?\s*(\d{1,2})[点时]"
)


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtractedCandidate:
    """Raw extraction result before wrapping into ScheduleCandidate."""

    title: str
    start_date: str | None = None
    start_time: str | None = None
    end_date: str | None = None
    end_time: str | None = None
    date_text: str | None = None
    confidence: float = 0.0
    matched_keyword: str | None = None
    evidence_text: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_candidates_from_text(
    text: str,
    *,
    doc_id: str = "",
    chunk_id: str = "",
    source: str = "",
) -> list[ScheduleCandidate]:
    """Extract schedule candidates from a single chunk text.

    Returns an empty list if no date+keyword or date+time pattern is found.
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    candidates: list[ScheduleCandidate] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        extracted = _extract_from_line(line)
        if extracted is None:
            continue

        dedup_key = _build_dedup_key(doc_id, chunk_id, extracted)
        now = _utc_now_iso()
        candidate = ScheduleCandidate(
            id=uuid4().hex,
            title=extracted.title,
            start_date=extracted.start_date,
            start_time=extracted.start_time,
            end_date=extracted.end_date,
            end_time=extracted.end_time,
            date_text=extracted.date_text,
            location=None,
            description=extracted.evidence_text,
            source_id=doc_id,
            doc_id=doc_id,
            chunk_id=chunk_id,
            source=source,
            evidence_text=extracted.evidence_text,
            confidence=extracted.confidence,
            status="pending",
            dedup_key=dedup_key,
            created_at=now,
            updated_at=now,
        )
        candidates.append(candidate)

    return candidates


# ---------------------------------------------------------------------------
# Internal extraction
# ---------------------------------------------------------------------------

def _extract_from_line(line: str) -> ExtractedCandidate | None:
    """Try to extract a schedule candidate from one line of text.

    Strategy:
    - Absolute date + Time + Keyword → high confidence (0.9)
    - Absolute date + Keyword → medium confidence (0.7)
    - Absolute date + Time → medium-low confidence (0.6)
    - Absolute date only → skip (avoid false positives)
    - Weekday + Time + Keyword → medium confidence (0.7)
    - Weekday + Time → medium-low confidence (0.5)
    - Weekday + Keyword → medium-low confidence (0.5)
    - Weekday only → skip (avoid false positives)
    - Keyword only → skip (avoid false positives)
    """
    date_result = _extract_date(line)
    time_result = _extract_time(line)
    keyword = _extract_keyword(line)

    has_date = date_result is not None
    has_time = time_result is not None
    has_keyword = keyword is not None

    # Nothing useful
    if not has_date and not has_keyword:
        return None

    # No date at all (not even weekday) — skip
    if not has_date:
        return None

    # Distinguish absolute date vs weekday-only
    has_absolute_date = date_result is not None and date_result[0] is not None
    has_weekday_only = date_result is not None and date_result[0] is None

    # Absolute date path
    if has_absolute_date:
        if has_time and has_keyword:
            confidence = 0.9
        elif has_keyword:
            confidence = 0.7
        elif has_time:
            confidence = 0.6
        else:
            # Date only — skip
            return None
        start_date = date_result[0]
    # Weekday-only path — need at least time or keyword
    elif has_weekday_only:
        if not has_time and not has_keyword:
            return None
        if has_time and has_keyword:
            confidence = 0.7
        elif has_time:
            confidence = 0.5
        else:
            confidence = 0.5
        start_date = None
    else:
        return None

    # Build result
    date_text_raw = date_result[1] if date_result else None
    start_time = time_result[0] if time_result else None
    end_time = time_result[1] if time_result else None

    title = _generate_title(line, date_text_raw, start_time, keyword)

    return ExtractedCandidate(
        title=title,
        start_date=start_date,
        start_time=start_time,
        end_time=end_time,
        date_text=date_text_raw,
        confidence=confidence,
        matched_keyword=keyword,
        evidence_text=line,
    )


def _extract_date(text: str) -> tuple[str, str] | None:
    """Extract date, return (normalized_date, date_text) or None."""

    # ISO date
    m = _DATE_ISO.search(text)
    if m:
        normalized = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return normalized, m.group(0)

    # Slash date
    m = _DATE_SLASH.search(text)
    if m:
        normalized = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return normalized, m.group(0)

    # Chinese full date
    m = _DATE_CN_FULL.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        normalized = f"{y:04d}-{mo:02d}-{d:02d}"
        return normalized, m.group(0)

    # English date
    m = _DATE_EN.search(text)
    if m:
        month_str = m.group(1)[:3].lower()
        month = _MONTH_NAMES.get(month_str)
        if month:
            day = int(m.group(2))
            year = int(m.group(3))
            normalized = f"{year:04d}-{month:02d}-{day:02d}"
            return normalized, m.group(0)

    # Chinese month-day (no year — use current year)
    m = _DATE_CN_MD.search(text)
    if m:
        now = datetime.now(timezone.utc)
        month, day = int(m.group(1)), int(m.group(2))
        normalized = f"{now.year:04d}-{month:02d}-{day:02d}"
        return normalized, m.group(0)

    # Weekday — return as date_text only, no absolute date
    m = _WEEKDAY_CN.search(text)
    if m:
        return None, m.group(0)

    return None


def _extract_time(text: str) -> tuple[str, str | None] | None:
    """Extract time, return (start_time, end_time) or None."""

    # Time range: 9:00-11:00
    m = _TIME_RANGE.search(text)
    if m:
        return m.group(1), m.group(2)

    # Chinese time range
    m = _TIME_CN_RANGE.search(text)
    if m:
        period1 = m.group(1) or ""
        h1 = int(m.group(2))
        period2 = m.group(3) or period1
        h2 = int(m.group(4))
        h1 = _normalize_hour(h1, period1)
        h2 = _normalize_hour(h2, period2)
        return f"{h1:02d}:00", f"{h2:02d}:00"

    # 24h time
    m = _TIME_24H.search(text)
    if m:
        return f"{m.group(1)}:{m.group(2)}", None

    # Chinese time point
    m = _TIME_CN.search(text)
    if m:
        period = m.group(1) or ""
        hour = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else 0
        hour = _normalize_hour(hour, period)
        return f"{hour:02d}:{minute:02d}", None

    return None


def _normalize_hour(hour: int, period: str) -> int:
    """Normalize 12h Chinese time to 24h."""
    if period in ("下午", "晚上") and hour < 12:
        return hour + 12
    if period in ("上午", "早上", "凌晨") and hour == 12:
        return 0
    if period == "中午" and hour == 12:
        return 12
    return hour


def _extract_keyword(text: str) -> str | None:
    """Return the first matched schedule keyword, or None."""
    text_lower = text.lower()
    for kw in _KEYWORDS_LOWER:
        if kw in text_lower:
            return kw
    return None


def _generate_title(
    line: str,
    date_text: str | None,
    time_text: str | None,
    keyword: str | None,
) -> str:
    """Generate a conservative title from evidence text."""
    title = line
    # Strip date patterns
    for pattern in (_DATE_ISO, _DATE_SLASH, _DATE_CN_FULL, _DATE_CN_MD, _DATE_EN, _WEEKDAY_CN):
        title = pattern.sub("", title)
    # Strip time patterns
    for pattern in (_TIME_RANGE, _TIME_CN_RANGE, _TIME_24H, _TIME_CN):
        title = pattern.sub("", title)
    # Strip punctuation
    title = re.sub(r"[，,：:;；\-]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -")

    if len(title) >= 2:
        return title[:80]

    # Fallback: keyword + date
    parts = []
    if keyword:
        parts.append(keyword)
    if date_text:
        parts.append(f"({date_text})")
    if parts:
        return " ".join(parts)

    return line[:80]


def _build_dedup_key(
    doc_id: str,
    chunk_id: str,
    extracted: ExtractedCandidate,
) -> str:
    """Build a deterministic dedup key for a candidate."""
    parts = [
        doc_id,
        chunk_id,
        extracted.start_date or "",
        extracted.start_time or "",
        extracted.date_text or "",
        _normalize_title_for_dedup(extracted.title),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _normalize_title_for_dedup(title: str) -> str:
    """Normalize title for dedup: lowercase, strip whitespace."""
    return re.sub(r"\s+", " ", title.strip().lower())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
