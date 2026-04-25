"""Safe, structured workflow trace helpers for retrieval-driven use cases."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.rag.retrieval_models import RetrievalFilters

SOURCE_PREVIEW_LIMIT = 5


def source_scope_trace(filters: RetrievalFilters | None) -> dict[str, object]:
    sources = tuple(filters.sources) if filters is not None else ()
    return {
        "has_explicit_source_filter": bool(sources),
        "selected_sources_count": len(sources),
        "selected_sources_preview": list(sources[:SOURCE_PREVIEW_LIMIT]),
    }


def final_source_summary(records) -> list[dict[str, object]]:
    grouped: dict[str, list[Any]] = {}
    for record in records or []:
        source = str(getattr(record, "source", None) or _record_get(record, "source") or "").strip()
        if not source:
            continue
        grouped.setdefault(source, []).append(record)

    summaries: list[dict[str, object]] = []
    for source, items in grouped.items():
        pages = [
            page
            for record in items
            for page in (
                _record_get(record, "page_start") or _record_get(record, "page"),
                _record_get(record, "page_end"),
            )
            if isinstance(page, int)
        ]
        section_titles = [
            str(section)
            for record in items
            for section in (
                _record_get(record, "section_title"),
                _record_get(record, "section"),
            )
            if section
        ]
        item: dict[str, object] = {
            "source": source,
            "citation_count": len(items),
        }
        if pages:
            item["page_range"] = [min(pages), max(pages)]
        if section_titles:
            item["section_title"] = Counter(section_titles).most_common(1)[0][0]
        summaries.append(item)
    return summaries


def build_trace_warnings(
    *,
    citations,
    structured_ref_intent_detected: bool = False,
    structured_ref_lexical_injection_applied: bool = False,
    local_doc_intent_detected: bool = False,
    local_doc_priority_applied: bool = False,
) -> list[str]:
    warnings: list[str] = []
    citation_list = list(citations or [])
    if not citation_list:
        warnings.append("no_citations")
    sources = {str(_record_get(citation, "source") or "") for citation in citation_list}
    sources.discard("")
    if len(sources) > 1:
        warnings.append("mixed_sources")
    if citation_list and not any(_record_get(citation, "window_chunk_count") for citation in citation_list):
        warnings.append("no_evidence_window")
    if any(bool(_record_get(citation, "is_hit_only_fallback")) for citation in citation_list):
        warnings.append("fallback_hit_only")
    if structured_ref_intent_detected and not structured_ref_lexical_injection_applied:
        warnings.append("structured_ref_no_lexical_candidate")
    if local_doc_intent_detected and not local_doc_priority_applied:
        warnings.append("local_doc_intent_no_markdown_candidate")
    return warnings


def _record_get(record, key: str):
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)
