"""Unit tests for schedule candidate extractor."""

import pytest

from app.schedule.extractor import (
    extract_candidates_from_text,
    _extract_date,
    _extract_time,
    _extract_keyword,
    _generate_title,
)


class TestExtractDate:
    def test_iso_date(self):
        result = _extract_date("会议安排在 2026-05-20 下午")
        assert result is not None
        assert result[0] == "2026-05-20"
        assert result[1] == "2026-05-20"

    def test_slash_date(self):
        result = _extract_date("截止日期 2026/05/20")
        assert result is not None
        assert result[0] == "2026-05-20"

    def test_chinese_full_date(self):
        result = _extract_date("2026年5月20日答辩")
        assert result is not None
        assert result[0] == "2026-05-20"
        assert result[1] == "2026年5月20日"

    def test_chinese_month_day(self):
        result = _extract_date("5月20日提交论文")
        assert result is not None
        assert "-05-20" in result[0]
        assert result[1] == "5月20日"

    def test_english_date(self):
        result = _extract_date("May 20, 2026 deadline")
        assert result is not None
        assert result[0] == "2026-05-20"
        assert result[1] == "May 20, 2026"

    def test_english_date_no_comma(self):
        result = _extract_date("May 20 2026 meeting")
        assert result is not None
        assert result[0] == "2026-05-20"

    def test_weekday_returns_none_date(self):
        result = _extract_date("周五开会")
        assert result is not None
        assert result[0] is None
        assert "周五" in result[1]

    def test_no_date(self):
        result = _extract_date("今天天气不错")
        assert result is None


class TestExtractTime:
    def test_24h_time(self):
        result = _extract_time("14:30 开始")
        assert result is not None
        assert result[0] == "14:30"
        assert result[1] is None

    def test_time_range(self):
        result = _extract_time("9:00-11:00 会议")
        assert result is not None
        assert result[0] == "9:00"
        assert result[1] == "11:00"

    def test_chinese_time_am(self):
        result = _extract_time("上午9点开会")
        assert result is not None
        assert result[0] == "09:00"

    def test_chinese_time_pm(self):
        result = _extract_time("下午2点答辩")
        assert result is not None
        assert result[0] == "14:00"

    def test_chinese_time_range(self):
        result = _extract_time("上午9点-11点讨论")
        assert result is not None
        assert result[0] == "09:00"
        assert result[1] == "11:00"

    def test_no_time(self):
        result = _extract_time("今天开会")
        assert result is None


class TestExtractKeyword:
    def test_chinese_keyword(self):
        assert _extract_keyword("明天有答辩") == "答辩"
        assert _extract_keyword("提交论文截止") == "截止"
        assert _extract_keyword("下午有个会议") == "会议"

    def test_english_keyword(self):
        assert _extract_keyword("deadline is tomorrow") == "deadline"
        assert _extract_keyword("Meeting at 3pm") == "meeting"

    def test_no_keyword(self):
        assert _extract_keyword("今天天气不错") is None


class TestExtractCandidatesFromText:
    def test_date_and_keyword_generates_candidate(self):
        text = "2026-05-20 答辩"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        c = candidates[0]
        assert c.start_date == "2026-05-20"
        assert c.confidence == 0.7
        assert c.status == "pending"
        assert c.doc_id == "d1"
        assert c.chunk_id == "c1"
        assert c.source == "test.md"
        assert c.evidence_text == text

    def test_date_time_keyword_high_confidence(self):
        text = "2026-05-20 14:30 答辩"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.9
        assert candidates[0].start_time == "14:30"

    def test_date_time_medium_low_confidence(self):
        text = "2026-05-20 14:30"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.6

    def test_date_only_no_candidate(self):
        text = "2026-05-20"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 0

    def test_keyword_only_no_candidate(self):
        text = "今天有个会议"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 0

    def test_no_relevant_text(self):
        text = "这是一段普通文本，没有任何日期或关键词。"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 0

    def test_empty_text(self):
        assert extract_candidates_from_text("", doc_id="d1", chunk_id="c1", source="test.md") == []

    def test_multiline_text(self):
        text = "第一行普通文本\n2026-05-20 答辩\n第三行普通文本"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].start_date == "2026-05-20"

    def test_chinese_date_with_keyword(self):
        text = "5月20日提交论文"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert "-05-20" in candidates[0].start_date

    def test_english_date_with_keyword(self):
        text = "May 20, 2026 interview"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].start_date == "2026-05-20"

    def test_time_range_extraction(self):
        text = "2026-05-20 9:00-11:00 会议"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].start_time == "9:00"
        assert candidates[0].end_time == "11:00"

    def test_candidate_has_dedup_key(self):
        text = "2026-05-20 答辩"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].dedup_key != ""

    def test_weekday_only_no_candidate(self):
        """只有周五，无时间无关键词 — 不生成候选"""
        text = "周五"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 0

    def test_weekday_with_keyword_generates_candidate(self):
        """周五 + 关键词 — 生成候选，start_date=None"""
        text = "周五答辩"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        c = candidates[0]
        assert c.start_date is None
        assert c.date_text is not None and "周五" in c.date_text
        assert c.confidence == 0.5

    def test_weekday_with_time_and_keyword_generates_candidate(self):
        """周五下午2点答辩 — 生成候选，confidence=0.7"""
        text = "周五下午2点答辩"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        c = candidates[0]
        assert c.start_date is None
        assert "周五" in (c.date_text or "")
        assert c.start_time == "14:00"
        assert c.confidence == 0.7

    def test_weekday_with_time_range_and_keyword(self):
        """星期五 9:00-11:00 meeting — 生成候选"""
        text = "星期五 9:00-11:00 meeting"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        c = candidates[0]
        assert c.start_date is None
        assert "星期五" in (c.date_text or "")
        assert c.start_time == "9:00"
        assert c.end_time == "11:00"
        assert c.confidence == 0.7

    def test_weekday_with_time_only_generates_candidate(self):
        """周五 14:30 — 有时间无关键词，生成候选"""
        text = "周五 14:30"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        c = candidates[0]
        assert c.start_date is None
        assert c.start_time == "14:30"
        assert c.confidence == 0.5

    def test_chinese_full_date_with_keyword(self):
        text = "2026年5月20日下午2点答辩"
        candidates = extract_candidates_from_text(text, doc_id="d1", chunk_id="c1", source="test.md")
        assert len(candidates) == 1
        assert candidates[0].start_date == "2026-05-20"
        assert candidates[0].start_time == "14:00"
        assert candidates[0].confidence == 0.9
