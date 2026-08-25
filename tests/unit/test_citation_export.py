"""Unit tests for citation format export (PRD FR-4)."""

from __future__ import annotations

import pytest

from app.services.citation_export_service import (
    CitationExportFormat,
    format_citation_entries,
    format_citation_entry,
    normalize_entry_fields,
)

FULL_ENTRY = {
    "title": "Efficient Retrieval-Augmented Generation",
    "authors": "Wang Rui; Li Ming; Sarah Chen",
    "year": 2021,
    "container": "Journal of Examples",
    "pages": "101-115",
    "doi": "10.1000/example",
}


class TestFormatters:
    def test_bibtex_full_entry(self):
        result = format_citation_entry(FULL_ENTRY, CitationExportFormat.BIBTEX)
        assert result.text.startswith("@misc{wang2021efficient,")
        assert "title = {Efficient Retrieval-Augmented Generation}" in result.text
        assert "author = {Wang Rui and Li Ming and Sarah Chen}" in result.text
        assert "year = {2021}" in result.text
        assert result.missing == ()

    def test_gbt7714_full_entry(self):
        result = format_citation_entry(FULL_ENTRY, "gbt7714")
        assert result.text.startswith("Wang Rui, Li Ming, Sarah Chen. Efficient Retrieval-Augmented Generation[Z]")
        assert "Journal of Examples: 2021: 101-115" in result.text
        assert "DOI:10.1000/example" in result.text

    def test_gbt7714_more_than_three_authors_uses_deng(self):
        entry = {**FULL_ENTRY, "authors": "A B; C D; E F; G H"}
        result = format_citation_entry(entry, "gbt7714")
        assert result.text.startswith("A B, C D, E F等.")

    def test_apa_full_entry(self):
        result = format_citation_entry(FULL_ENTRY, "apa")
        assert "Wang Rui, Li Ming & Sarah Chen (2021). Efficient Retrieval-Augmented Generation." in result.text
        assert "https://doi.org/10.1000/example" in result.text

    def test_missing_fields_degrade_with_markers(self):
        result = format_citation_entry({}, "apa")
        text = result.text
        assert "(no author)" in text
        assert "n.d." in text
        assert "(untitled)" in text
        assert set(result.missing) == {"title", "authors", "year"}

    def test_bibtex_degrades_without_year(self):
        result = format_citation_entry({"title": "Solo"}, "bibtex")
        assert "year =" not in result.text
        assert "missing" not in result.text  # bibtex omits rather than marks

    def test_url_switches_gbt_type(self):
        result = format_citation_entry({**FULL_ENTRY, "url": "https://example.com/paper"}, "gbt7714")
        assert "[EB/OL]" in result.text
        assert "https://example.com/paper" in result.text


class TestNormalize:
    def test_author_list_passthrough(self):
        fields = normalize_entry_fields({"authors": ["Wang Rui", "Li Ming"], "title": "T", "year": 2020})
        assert fields["authors"] == ["Wang Rui", "Li Ming"]

    def test_doc_authors_and_doc_year_fallbacks(self):
        fields = normalize_entry_fields({"doc_authors": "王睿；李明", "doc_year": 2022})
        assert fields["authors"] == ["王睿", "李明"]
        assert fields["year"] == 2022

    def test_page_normalization(self):
        fields = normalize_entry_fields({"page": "12–14"})
        assert fields["pages"] == "12-14"


class TestBatchExport:
    def test_batch_shape(self):
        result = format_citation_entries([FULL_ENTRY, {}], "bibtex")
        assert result["format"] == "bibtex"
        assert result["count"] == 2
        assert "\n\n" in str(result["text"])
        items = result["items"]
        assert items[0]["missing"] == []
        assert set(items[1]["missing"]) == {"title", "authors", "year"}

    def test_unknown_format_rejected(self):
        with pytest.raises(ValueError):
            CitationExportFormat("mla8")
