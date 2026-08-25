"""Unit tests for schedule-candidate ICS export (PRD FR-9)."""

from __future__ import annotations

from app.schedule.models import ScheduleCandidate
from app.services.schedule_ics_service import build_ics_calendar, summarize_export


def _candidate(**overrides) -> ScheduleCandidate:
    base = dict(
        id="cand-1",
        title="组会汇报, 周三",
        start_date="2026-03-04",
        start_time="14:00",
        end_date="2026-03-04",
        end_time="15:30",
        location="会议室 A; 3楼",
        evidence_text="3月4日下午2点组会",
        source="notes/meeting.md",
        status="confirmed",
    )
    base.update(overrides)
    return ScheduleCandidate(**base)


class TestBuildIcs:
    def test_contains_calendar_wrapper_and_event(self):
        text = build_ics_calendar([_candidate()])
        assert text.startswith("BEGIN:VCALENDAR")
        assert "VERSION:2.0" in text
        assert "BEGIN:VEVENT" in text and "END:VEVENT" in text
        assert text.endswith("END:VCALENDAR\r\n")

    def test_datetime_fields(self):
        text = build_ics_calendar([_candidate()])
        assert "DTSTART:20260304T140000" in text
        assert "DTEND:20260304T153000" in text

    def test_special_chars_escaped(self):
        text = build_ics_calendar([_candidate()])
        assert "SUMMARY:组会汇报\\, 周三" in text
        assert "LOCATION:会议室 A\\; 3楼" in text

    def test_all_day_candidate(self):
        text = build_ics_calendar([_candidate(start_time=None, end_time=None)])
        assert "DTSTART;VALUE=DATE:20260304" in text
        # DTEND is exclusive per RFC 5545.
        assert "DTEND;VALUE=DATE:20260305" in text

    def test_dateless_candidates_are_skipped_but_calendar_valid(self):
        text = build_ics_calendar([_candidate(start_date=None), _candidate(id="c2", start_date="无效")])
        assert "no dated candidates" in text
        assert "DTSTART;VALUE=DATE:" in text

    def test_default_one_hour_duration_when_end_missing(self):
        text = build_ics_calendar([_candidate(end_date=None, end_time=None)])
        assert "DTSTART:20260304T140000" in text
        assert "DTEND:20260304T150000" in text

    def test_description_includes_evidence_and_source(self):
        text = build_ics_calendar([_candidate()])
        assert "DESCRIPTION:" in text
        assert "notes/meeting.md" in text


class TestSummarizeExport:
    def test_counts(self):
        summary = summarize_export(
            [
                _candidate(),
                _candidate(id="c2", start_date="2026-05-01", status="pending"),
                _candidate(id="c3", start_date=None),
            ]
        )
        assert summary == {"total": 3, "dated": 2}
