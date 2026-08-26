"""ICS calendar export for schedule candidates (PRD FR-9).

Closes the schedule-candidate loop with the cheapest possible integration:
confirmed/pending candidates with parseable dates become an RFC 5545 calendar
the user downloads and imports into any calendar app — no OAuth, no write
access, keeping the human-review philosophy intact.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone

from app.schedule.models import ScheduleCandidate

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


def build_ics_calendar(candidates: Sequence[ScheduleCandidate]) -> str:
    """Build one VCALENDAR string covering candidates that have real dates."""

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MindDock//Schedule Candidates//EN",
        "CALSCALE:GREGORIAN",
    ]
    exported = 0
    stamp = _dtstamp_now()
    for candidate in candidates:
        event_lines = _event_lines(candidate, stamp)
        if event_lines is not None:
            lines.extend(event_lines)
            exported += 1

    if exported == 0:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:minddock-empty-{stamp}@minddock.local")
        lines.append(f"DTSTAMP:{stamp}")
        lines.append("SUMMARY:MindDock schedule export (no dated candidates)")
        lines.append("DTSTART;VALUE=DATE:" + datetime.now(timezone.utc).strftime("%Y%m%d"))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _event_lines(candidate: ScheduleCandidate, stamp: str) -> list[str] | None:
    start = _parse_datetime(candidate.start_date, candidate.start_time)
    if start is None:
        return None
    all_day = candidate.start_time is None and _DATE_RE.match(str(candidate.start_date)) is not None

    lines: list[str] = ["BEGIN:VEVENT"]
    lines.append(f"UID:{_escape(candidate.id or f'cand-{stamp}')}")
    lines.append(f"DTSTAMP:{stamp}")
    summary = candidate.title or "MindDock schedule candidate"
    lines.append(f"SUMMARY:{_escape(summary)}")

    if all_day:
        lines.append("DTSTART;VALUE=DATE:" + str(candidate.start_date).replace("-", ""))
        end_date = candidate.end_date or candidate.start_date
        end_value = str(end_date).replace("-", "") if _DATE_RE.match(str(end_date)) else str(candidate.start_date).replace("-", "")
        try:
            exclusive_end = (
                datetime.strptime(end_value, "%Y%m%d") + timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            exclusive_end = end_value
        lines.append(f"DTEND;VALUE=DATE:{exclusive_end}")
    else:
        lines.append("DTSTART:" + start.strftime("%Y%m%dT%H%M%S"))
        end = _parse_datetime(candidate.end_date, candidate.end_time)
        if end is None or end < start:
            end = start + timedelta(hours=1)
        lines.append("DTEND:" + end.strftime("%Y%m%dT%H%M%S"))

    if candidate.location:
        lines.append(f"LOCATION:{_escape(candidate.location)}")

    description_parts = [part for part in (candidate.description, candidate.evidence_text, candidate.source) if part]
    if description_parts:
        lines.append("DESCRIPTION:" + _escape(" \\n ".join(part.strip() for part in description_parts)))

    lines.append("END:VEVENT")
    return lines


def _parse_datetime(date_value: str | None, time_value: str | None) -> datetime | None:
    if not date_value or not _DATE_RE.match(str(date_value)):
        # Some candidates carry combined datetime strings.
        if date_value and _DATETIME_RE.match(str(date_value)):
            normalized = str(date_value).replace("T", " ")
            fmt = "%Y-%m-%d %H:%M:%S" if normalized.count(":") == 2 else "%Y-%m-%d %H:%M"
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                return None
        return None

    if time_value and _TIME_RE.match(str(time_value)):
        time_text = str(time_value)
        fmt_time = "%H:%M:%S" if time_text.count(":") == 2 else "%H:%M"
        try:
            parsed_time = datetime.strptime(time_text, fmt_time).time()
        except ValueError:
            return None
        return datetime.combine(
            datetime.strptime(str(date_value), "%Y-%m-%d").date(),
            parsed_time,
        )

    # Date-only: midnight anchor; caller decides all-day vs default duration.
    try:
        return datetime.combine(datetime.strptime(str(date_value), "%Y-%m-%d").date(), datetime.min.time())
    except ValueError:
        return None


def _escape(value: object) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\n", "\\n")
    return text


def _dtstamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def summarize_export(candidates: Iterable[ScheduleCandidate]) -> dict[str, int]:
    items = list(candidates)
    return {
        "total": len(items),
        "dated": sum(1 for c in items if c.start_date and _DATE_RE.match(str(c.start_date))),
    }
