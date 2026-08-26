"""Unit tests for academic front-matter metadata extraction and filters (PRD FR-3)."""

from __future__ import annotations

from app.api.schemas import MetadataFilters
from app.rag.frontmatter_metadata import (
    AcademicDocMetadata,
    extract_academic_metadata,
    is_academic_metadata_eligible,
)
from app.rag.retrieval_models import RetrievalFilters
from app.rag.vectorstore import _build_where, _candidate_fetch_k


EN_PAPER_HEAD = """Efficient Retrieval-Augmented Generation for Personal Knowledge Bases
Wang Rui, Li Ming and Sarah Chen
Department of Computer Science, Example University
rui@example.edu
Abstract
We study retrieval augmented generation over personal knowledge bases.
References [12] pp. 101-115 (2021).
"""

CN_PAPER_HEAD = """面向个人知识库的检索增强生成方法研究
王睿，李明
某某大学计算机学院
摘要：本文研究检索增强生成方法。
关键词：检索增强；知识库
"""


class TestExtraction:
    def test_extracts_year_and_authors_from_english_paper(self):
        meta = extract_academic_metadata(EN_PAPER_HEAD)
        assert meta.year == 2021
        assert meta.authors is not None
        lowered = meta.authors.lower()
        assert "wang rui" in lowered or "wang" in lowered
        assert "sarah chen" in lowered or "chen" in lowered

    def test_extracts_chinese_authors(self):
        meta = extract_academic_metadata(CN_PAPER_HEAD)
        assert meta.authors is not None
        assert "王睿" in meta.authors
        assert "李明" in meta.authors
        # Year absent in this sample head.
        assert meta.year is None

    def test_empty_text_yields_empty_metadata(self):
        meta = extract_academic_metadata("")
        assert meta.authors is None and meta.year is None

    def test_metadata_pairs_omit_missing_fields(self):
        empty = AcademicDocMetadata().to_metadata_pairs()
        assert empty == {}
        full = AcademicDocMetadata(authors="A; B", year=2020).to_metadata_pairs()
        assert full == {"doc_authors": "A; B", "doc_year": 2020}


class TestEligibility:
    def test_file_text_sources_are_eligible(self):
        assert is_academic_metadata_eligible(source_type="file", loader_name="pdf")
        assert is_academic_metadata_eligible(source_type="file", loader_name=None)

    def test_media_csv_and_url_sources_are_excluded(self):
        assert not is_academic_metadata_eligible(source_type="url", loader_name="url")
        assert not is_academic_metadata_eligible(source_type="file", loader_name="csv")
        assert not is_academic_metadata_eligible(source_type="file", loader_name="audio.transcribe")
        assert not is_academic_metadata_eligible(source_type="file", loader_name="image.ocr")


def _metadata(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "source": "papers/example.pdf",
        "source_type": "file",
        "title": "Example Paper",
        "section": "",
        "page": 3,
        "doc_authors": "Wang Rui; Li Ming; Sarah Chen",
        "doc_year": 2021,
    }
    base.update(overrides)
    return base


class TestAcademicFilterMatching:
    def test_author_substring_match_is_case_insensitive(self):
        filters = RetrievalFilters(authors=("wang rui",))
        assert filters.matches_metadata(_metadata()) is True

    def test_second_author_also_matches(self):
        filters = RetrievalFilters(authors=("Sarah Chen",))
        assert filters.matches_metadata(_metadata()) is True

    def test_unknown_author_is_filtered_out(self):
        filters = RetrievalFilters(authors=("Nobody",))
        assert filters.matches_metadata(_metadata()) is False

    def test_chunk_without_doc_authors_fails_explicit_filter(self):
        filters = RetrievalFilters(authors=("Wang Rui",))
        assert filters.matches_metadata(_metadata(doc_authors="")) is False

    def test_year_range_matching(self):
        within = RetrievalFilters(year_from=2020, year_to=2022)
        before = RetrievalFilters(year_from=2022)
        missing = RetrievalFilters(year_from=2000)
        assert within.matches_metadata(_metadata()) is True
        assert before.matches_metadata(_metadata()) is False
        assert missing.matches_metadata(_metadata(doc_year="")) is False

    def test_has_academic_filters_flag(self):
        assert RetrievalFilters(authors=("x",)).has_academic_filters() is True
        assert RetrievalFilters(year_from=2020).has_academic_filters() is True
        assert RetrievalFilters().has_academic_filters() is False


class TestWhereAndFetchIntegration:
    def test_where_flat_without_academic_filters(self):
        where = _build_where(RetrievalFilters(section="intro"))
        assert where == {"section": "intro"}

    def test_year_range_composes_and_conditions(self):
        where = _build_where(RetrievalFilters(section="intro", year_from=2020, year_to=2021))
        assert set(where.keys()) == {"$and"}
        conditions = where["$and"]
        assert {"section": "intro"} in conditions
        assert {"doc_year": {"$gte": 2020, "$lte": 2021}} in conditions

    def test_single_year_bound(self):
        where = _build_where(RetrievalFilters(year_from=2019))
        assert where == {"$and": [{"doc_year": {"$gte": 2019}}]}

    def test_author_filter_inflates_candidate_pool(self):
        plain = _candidate_fetch_k(total=1000, top_k=5, filters=RetrievalFilters())
        authors = _candidate_fetch_k(total=1000, top_k=5, filters=RetrievalFilters(authors=("wang",)))
        years = _candidate_fetch_k(total=1000, top_k=5, filters=RetrievalFilters(year_from=2020))
        assert plain == 5
        assert authors == 50
        # Year filtering happens in the where clause, so no inflation needed.
        assert years == 5


class TestSchemaRoundTrip:
    def test_metadata_filters_to_retrieval_filters(self):
        payload = MetadataFilters.model_validate(
            {"authors": [" Wang Rui ", ""], "year_from": 2019, "year_to": 2024}
        )
        filters = payload.to_retrieval_filters()
        assert filters.authors == ("Wang Rui",)
        assert filters.year_from == 2019
        assert filters.year_to == 2024

    def test_year_range_validation(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MetadataFilters.model_validate({"year_from": 2024, "year_to": 2019})
