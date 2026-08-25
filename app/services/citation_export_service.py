"""Citation format export: BibTeX / GB/T 7714 / APA (PRD FR-4).

Pure deterministic formatters over citation payload dicts. Missing fields
degrade to explicit placeholders and are reported back so the UI can mark
incomplete entries instead of silently producing wrong references.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

_BIBTYPE_DEFAULT = "misc"
_CITEKEY_STRIP_RE = re.compile(r"[^A-Za-z0-9]")


class CitationExportFormat(StrEnum):
    """Supported citation export formats."""

    BIBTEX = "bibtex"
    GBT7714 = "gbt7714"
    APA = "apa"


@dataclass(frozen=True)
class FormattedCitation:
    """One formatted citation plus degradation notes."""

    index: int
    text: str
    missing: tuple[str, ...] = ()

    def to_api_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "text": self.text,
            "missing": list(self.missing),
        }


def normalize_entry_fields(entry: Mapping[str, object]) -> dict[str, object]:
    """Normalize a raw citation payload into exporter field names."""

    authors_raw = entry.get("authors")
    if authors_raw is None:
        authors_raw = entry.get("doc_authors") or entry.get("author")

    if isinstance(authors_raw, (list, tuple)):
        author_list = [str(a).strip() for a in authors_raw if str(a).strip()]
    else:
        text = str(authors_raw or "").strip()
        if not text:
            author_list = []
        else:
            parts = re.split(r"[;；]|,\s(?=[A-Z][a-z]*\b)|，", text)
            author_list = [part.strip() for part in parts if part.strip()]

    title = str(entry.get("title") or "").strip()
    year_raw = entry.get("year") or entry.get("doc_year")
    try:
        year = int(str(year_raw)) if year_raw not in (None, "") else None
    except (TypeError, ValueError):
        year = None

    container = str(
        entry.get("container")
        or entry.get("journal")
        or entry.get("venue")
        or ""
    ).strip()
    source = str(entry.get("source") or "").strip()

    pages_raw = entry.get("pages") or entry.get("page")
    pages = _normalize_pages(pages_raw)

    return {
        "title": title,
        "authors": author_list,
        "year": year,
        "container": container or source,
        "pages": pages,
        "url": str(entry.get("url") or "").strip() or None,
        "doi": str(entry.get("doi") or "").strip() or None,
        "publisher": str(entry.get("publisher") or "").strip() or None,
    }


def format_citation_entry(entry: Mapping[str, object], fmt: CitationExportFormat | str) -> FormattedCitation:
    """Format one citation entry in the requested style."""

    style = CitationExportFormat(fmt)
    fields = normalize_entry_fields(entry)
    missing = [
        name
        for name, value in (
            ("title", fields["title"]),
            ("authors", "; ".join(fields["authors"]) if fields["authors"] else ""),
            ("year", fields["year"]),
        )
        if not value
    ]

    if style == CitationExportFormat.BIBTEX:
        text = _format_bibtex(fields)
    elif style == CitationExportFormat.GBT7714:
        text = _format_gbt7714(fields)
    else:
        text = _format_apa(fields)
    return FormattedCitation(index=int(entry.get("_index", 0)) or 0, text=text, missing=tuple(missing))


def format_citation_entries(entries: Sequence[Mapping[str, object]], fmt: CitationExportFormat | str) -> dict[str, object]:
    """Format many entries. BibTeX output joins entries with blank lines."""

    style = CitationExportFormat(fmt)
    formatted = [
        format_citation_entry({**entry, "_index": index}, style)
        for index, entry in enumerate(entries, start=1)
    ]
    if style == CitationExportFormat.BIBTEX:
        combined = "\n\n".join(item.text for item in formatted)
    else:
        combined = "\n".join(f"{index}. {item.text}" for index, item in enumerate(formatted, start=1))
    return {
        "format": style.value,
        "count": len(formatted),
        "text": combined,
        "items": [item.to_api_dict() for item in formatted],
    }


# ---------------------------------------------------------------------------
# Per-style templates
# ---------------------------------------------------------------------------


def _format_bibtex(fields: dict[str, object]) -> str:
    authors = fields["authors"] or ["(no author)"]
    title = fields["title"] or "(untitled)"
    key = _citekey(authors[0], fields["year"], title)
    lines = [f"@{_BIBTYPE_DEFAULT}{{{key},"]
    lines.append(f"  title = {{{title}}},")
    joined_authors = " and ".join(str(author) for author in authors)
    lines.append(f"  author = {{{joined_authors}}},")
    if fields["year"] is not None:
        lines.append(f"  year = {{{fields['year']}}},")
    if fields["container"]:
        lines.append(f"  howpublished = {{{fields['container']}}},")
    if fields["pages"]:
        lines.append(f"  pages = {{{fields['pages']}}},")
    if fields["doi"]:
        lines.append(f"  doi = {{{fields['doi']}}},")
    if fields["url"]:
        lines.append(f"  url = {{{fields['url']}}},")
    lines.append("}")
    return "\n".join(lines)


def _format_gbt7714(fields: dict[str, object]) -> str:
    authors = fields["authors"]
    author_text = ", ".join(str(a) for a in authors[:3]) + ("等" if len(authors) > 3 else "")
    if not author_text:
        author_text = "[无作者]"
    title = fields["title"] or "(无题名)"
    doc_type = "[EB/OL]" if fields["url"] else "[Z]"
    core = f"{author_text}. {title}{doc_type}"
    tail_parts: list[str] = []
    if fields["container"]:
        tail_parts.append(str(fields["container"]))
    if fields["year"] is not None:
        tail_parts.append(str(fields["year"]))
    if fields["pages"]:
        tail_parts.append(f"{fields['pages']}页" if not str(fields["pages"]).endswith("-") else f"{fields['pages']}")
    tail = ": ".join(tail_parts) if tail_parts else ""
    text = f"{core}. {tail}." if tail else f"{core}."
    if fields["doi"]:
        text += f" DOI:{fields['doi']}."
    if fields["url"]:
        text += f" {fields['url']}."
    return text


def _format_apa(fields: dict[str, object]) -> str:
    authors = fields["authors"]
    if authors:
        if len(authors) == 1:
            author_text = str(authors[0])
        elif len(authors) <= 6:
            author_text = ", ".join(str(a) for a in authors[:-1]) + f" & {authors[-1]}"
        else:
            author_text = ", ".join(str(a) for a in authors[:6]) + ", et al."
    else:
        author_text = "(no author)"
    year_text = str(fields["year"]) if fields["year"] is not None else "n.d."
    title = fields["title"] or "(untitled)"
    text = f"{author_text} ({year_text}). {title}."
    if fields["container"]:
        text += f" {fields['container']}."
    if fields["pages"]:
        text += f" {fields['pages']}."
    if fields["doi"]:
        text += f" https://doi.org/{fields['doi']}"
    elif fields["url"]:
        text += f" {fields['url']}"
    return text


def _citekey(first_author: str, year: object, title: str) -> str:
    surname = _CITEKEY_STRIP_RE.sub("", str(first_author).split()[0] if str(first_author).split() else "anon")
    year_part = str(year) if year is not None else "nd"
    title_word = next((word for word in re.findall(r"[A-Za-z]+", title)), "item")
    return f"{surname.lower()}{year_part}{title_word.lower()}"


def _normalize_pages(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    # Normalize "12-14" / "12–14" ranges and single numbers.
    normalized = text.replace("–", "-").replace("—", "-")
    if re.fullmatch(r"\d+(-\d+)?", normalized):
        return normalized
    match = re.search(r"(\d+)\s*-\s*(\d+)", normalized)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return normalized or None
