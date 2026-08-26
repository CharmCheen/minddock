"""Review Workbench: multi-source related-work table generation (PRD FR-7, MVP).

Given a topic plus 2-5 selected sources, retrieves scoped evidence per source,
synthesizes an overview / comparison table / takeaways payload (``review.v1``),
and returns unified citations so every table cell stays clickable and
verifiable. LLM synthesis is optional; a deterministic extractive fallback
keeps the feature usable without any runtime.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.rag.retrieval_models import CitationRecord, RetrievalFilters
from app.rag.retrieval_models import RetrievedChunk
from app.services.citation_self_check import run_citation_self_check
from app.services.grounded_generation import build_citation, select_grounded_hits
from app.services.search_service import SearchService
from app.services.service_models import ServiceIssue, UseCaseMetadata, UseCaseTiming

logger = logging.getLogger(__name__)

_REVIEW_SCHEMA_NAME = "review.v1"
_MIN_SOURCES = 2
_MAX_SOURCES = 5
_MAX_CELLS_PER_ROW = _MAX_SOURCES
_FALLBACK_SENTENCE_LIMIT = 2
_INSUFFICIENT_MESSAGE = "Insufficient evidence to build the review workbench output."

_TABLE_JSON_RE = re.compile(r"\{.*\}", re.S)


@dataclass(frozen=True)
class ReviewWorkbenchRequest:
    """MVP review workbench request."""

    topic: str
    sources: tuple[str, ...]
    top_k: int = 6


@dataclass(frozen=True)
class ReviewWorkbenchResult:
    """Service-level result consumed by the API route."""

    answer_markdown: str
    payload: dict[str, Any]
    citations: list[CitationRecord]
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)

    @property
    def schema_name(self) -> str:
        return _REVIEW_SCHEMA_NAME


def run_review_workbench(
    request: ReviewWorkbenchRequest,
    *,
    search_service: SearchService | None = None,
    runtime=None,
) -> ReviewWorkbenchResult:
    """Run the MVP review pipeline: per-source retrieval → synthesis → payload."""

    started = time.perf_counter()
    search_service = search_service or SearchService()
    sources = tuple(s.strip() for s in request.sources if s.strip())[:_MAX_SOURCES]
    topic = request.topic.strip()

    warnings: list[str] = []
    if len(sources) < _MIN_SOURCES:
        warnings.append(f"review_needs_{_MIN_SOURCES}_sources")
    if not topic:
        return _insufficient(request, sources, ("empty_topic",), started)

    per_source_evidence, citations, source_warnings = _collect_source_evidence(
        search_service=search_service,
        topic=topic,
        sources=sources,
        top_k=max(3, int(request.top_k)),
    )
    warnings.extend(source_warnings)

    covered_sources = [source for source, hits in per_source_evidence.items() if hits]
    if len(covered_sources) < _MIN_SOURCES:
        return _insufficient(request, sources, warnings + ["insufficient_source_coverage"], started)

    synthesis = _synthesize(topic, per_source_evidence, citations, runtime=runtime)
    synthesis_layer = str(synthesis.get("llm_layer") or "unknown")
    if synthesis_layer != "completed":
        warnings.append("review_llm_fallback_extractive")

    payload = _build_payload(
        topic=topic,
        sources=sources,
        per_source_evidence=per_source_evidence,
        citations=citations,
        synthesis=synthesis,
    )
    markdown = _render_markdown(payload)
    # PRD v1.2 D-1: the LLM verification layer must receive the real runtime;
    # skipping it is a visible degradation, never a silent half-check.
    self_check = run_citation_self_check(answer_text=markdown, citations=citations, runtime=runtime)
    verification_layers = dict(self_check.layers)
    verify_llm_completed = verification_layers.get("llm") == "completed"
    if not verify_llm_completed:
        warnings.append(f"self_check_llm_{verification_layers.get('llm', 'unknown')}")

    # Honest quality signals (PRD v1.2 D-1): no hardcoded green. A clean pass
    # requires full source coverage, a passing self-check, AND both LLM layers
    # actually running; anything less degrades visibly.
    quality_reasons: list[str] = []
    low_confidence = False
    if len(covered_sources) < len(sources):
        low_confidence = True
        quality_reasons.append("partial_source_coverage")
    if self_check.overall != "pass":
        low_confidence = True
        quality_reasons.append(f"self_check_{self_check.overall}")
    full_llm = synthesis_layer == "completed" and verify_llm_completed
    if not full_llm:
        low_confidence = True
        quality_reasons.append("llm_layers_degraded")

    support_status = (
        "supported"
        if (not low_confidence and self_check.overall == "pass")
        else "partially_supported"
    )

    trace = {
        "operation": "review_workbench",
        "quality_ok": not low_confidence,
        "low_confidence": low_confidence,
        "quality_reasons": quality_reasons,
        "retry_count": 0,
        "max_retries": 0,
        "selected_sources_count": len(sources),
        "covered_sources_count": len(covered_sources),
        "final_citation_count": len(citations),
        "synthesis_llm_layer": synthesis_layer,
        "verification_layers": verification_layers,
        "citation_self_check": {"overall": self_check.overall, "counts": self_check.counts()},
        "trace_warnings": list(warnings),
    }

    metadata = UseCaseMetadata(
        retrieved_count=len(citations),
        mode="review_workbench",
        support_status=support_status,
        warnings=tuple(warnings),
        timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
        workflow_trace=trace,
        retrieval_stats=None,
    )
    return ReviewWorkbenchResult(
        answer_markdown=markdown,
        payload=payload,
        citations=citations,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _collect_source_evidence(
    *, search_service: SearchService, topic: str, sources: tuple[str, ...], top_k: int
) -> tuple[dict[str, list[RetrievedChunk]], list[CitationRecord], list[str]]:
    per_source: dict[str, list[RetrievedChunk]] = {}
    citations: list[CitationRecord] = []
    seen_chunk_ids: set[str] = set()
    warnings: list[str] = []

    for source in sources:
        filters = RetrievalFilters(sources=(source,))
        try:
            hits = search_service.retrieve(query=topic, top_k=top_k, filters=filters)
        except Exception as exc:
            logger.warning("Review workbench retrieval failed for %s: %s", source, exc)
            hits = []
            warnings.append(f"retrieval_failed:{source}")
        grounded = select_grounded_hits(hits).hits
        per_source[source] = grounded
        for hit in grounded:
            if hit.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(hit.chunk_id)
            record = build_citation(hit)
            citations.append(record)
    return per_source, citations, warnings


# ---------------------------------------------------------------------------
# Synthesis (LLM optional, extractive fallback deterministic)
# ---------------------------------------------------------------------------


def _synthesize(
    topic: str,
    per_source_evidence: dict[str, list[RetrievedChunk]],
    citations: list[CitationRecord],
    *,
    runtime,
) -> dict[str, Any]:
    fallback = _extractive_synthesis(per_source_evidence, citations)
    if runtime is None:
        fallback["llm_layer"] = "skipped_no_runtime"
        return fallback
    try:
        raw = runtime.invoke(
            prompt=_build_prompt(topic, per_source_evidence, citations),
            inputs={"task": "review_workbench"},
            fallback_query=f"Review topic: {topic}",
            fallback_evidence=[],
        )
        parsed = _parse_review_json(str(raw))
        parsed["llm_layer"] = "completed"
        return parsed
    except Exception as exc:
        logger.warning("Review workbench LLM synthesis failed: %s", exc)
        fallback["llm_layer"] = f"failed:{exc.__class__.__name__}"
        return fallback


def _build_prompt(topic: str, per_source_evidence: dict[str, list[RetrievedChunk]], citations: list[CitationRecord]) -> str:
    ref_to_index = {record.ref or record.chunk_id: i + 1 for i, record in enumerate(citations)}
    lines = [f"Topic: {topic}", "", "Per-source evidence:"]
    for source, hits in per_source_evidence.items():
        lines.append(f"- {source}:")
        for hit in hits[:3]:
            index = ref_to_index.get(hit.ref or hit.chunk_id, "")
            marker = f" [citation {index}]" if index else ""
            lines.append(f"  · {hit.text[:240]}{marker}")
    lines.append("")
    lines.append(
        'Return ONLY JSON: {"overview": "...", '
        '"table": [{"dimension": "...", "cells": [{"source": "...", "point": "...", "citation": <int|null>}]}], '
        '"takeaways": ["..."]}'
    )
    return "\n".join(lines)


def _parse_review_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    match = _TABLE_JSON_RE.search(text)
    if not match:
        raise ValueError("review llm response contained no JSON object")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("review llm response was not a JSON object")
    if not isinstance(data.get("table"), list):
        raise ValueError("review llm response missing table")
    return data


def _extractive_synthesis(
    per_source_evidence: dict[str, list[RetrievedChunk]],
    citations: list[CitationRecord],
) -> dict[str, Any]:
    ref_to_index = {record.ref or record.chunk_id: i + 1 for i, record in enumerate(citations)}
    overview_parts = []
    table_rows: list[dict[str, Any]] = []
    takeaways: list[str] = []

    dimensions_seen: list[str] = []
    for source, hits in per_source_evidence.items():
        if not hits:
            continue
        lead = hits[0]
        sentences = [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+|\n+", lead.text) if s.strip()]
        point = " ".join(sentences[:_FALLBACK_SENTENCE_LIMIT]) or lead.text[:200]
        overview_parts.append(f"{source}: {point}")
        dimension = (lead.section or lead.title or "Key points").strip() or "Key points"
        if dimension not in dimensions_seen:
            dimensions_seen.append(dimension)

    for dimension in dimensions_seen[:4]:
        cells = []
        for source, hits in per_source_evidence.items():
            match = next((h for h in hits if (h.section or h.title or "Key points").strip() == dimension), None)
            if match is None and hits:
                match = hits[0]
            if match is None:
                continue
            sentences = [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+|\n+", match.text) if s.strip()]
            cells.append(
                {
                    "source": source,
                    "point": " ".join(sentences[:_FALLBACK_SENTENCE_LIMIT])[:220],
                    "citation": ref_to_index.get(match.ref or match.chunk_id),
                }
            )
        table_rows.append({"dimension": dimension, "cells": cells[:_MAX_CELLS_PER_ROW]})

    for source, hits in list(per_source_evidence.items()):
        if hits:
            first = hits[0]
            index = ref_to_index.get(first.ref or first.chunk_id)
            takeaways.append(f"{source} leads with: {first.text.splitlines()[0][:120]} [citation {index}]")

    return {
        "overview": " ".join(overview_parts)[:800],
        "table": table_rows,
        "takeaways": takeaways[:5],
    }


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------


def _build_payload(
    *,
    topic: str,
    sources: tuple[str, ...],
    per_source_evidence: dict[str, list[RetrievedChunk]],
    citations: list[CitationRecord],
    synthesis: dict[str, Any],
) -> dict[str, Any]:
    table = []
    for row in synthesis.get("table", []) or []:
        cells = [
            {
                "source": str(cell.get("source") or ""),
                "point": str(cell.get("point") or ""),
                "citation": cell.get("citation"),
            }
            for cell in row.get("cells", [])
            if isinstance(cell, dict)
        ][:_MAX_CELLS_PER_ROW]
        table.append({"dimension": str(row.get("dimension") or ""), "cells": cells})

    return {
        "schema_name": _REVIEW_SCHEMA_NAME,
        "topic": topic,
        "sources": list(sources),
        "covered_sources": [s for s, hits in per_source_evidence.items() if hits],
        "overview": str(synthesis.get("overview") or ""),
        "table": table,
        "takeaways": [str(item) for item in (synthesis.get("takeaways") or [])][:8],
        "citation_count": len(citations),
        "llm_layer": synthesis.get("llm_layer", "unknown"),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Review: {payload['topic']}", ""]
    if payload.get("overview"):
        lines += [str(payload["overview"]), ""]
    rows = payload.get("table") or []
    if rows:
        header = "| Dimension | " + " | ".join(payload.get("sources") or []) + " |"
        sep = "|" + "---|" * (len(payload.get("sources") or []) + 1)
        lines += [header, sep]
        by_source_rows: dict[str, list[str]] = {}
        for row in rows:
            for cell in row.get("cells", []):
                citation = cell.get("citation")
                text = cell.get("point") or ""
                suffix = f" [{citation}]" if citation else ""
                by_source_rows.setdefault(row.get("dimension"), []).append(f"{cell.get('source')}: {text}{suffix}")
        for dimension, parts in by_source_rows.items():
            lines.append("| " + dimension + " | " + "<br>".join(parts) + " |")
        lines.append("")
    takeaways = payload.get("takeaways") or []
    if takeaways:
        lines.append("## Takeaways")
        lines.extend(f"- {item}" for item in takeaways)
    return "\n".join(lines)


def _insufficient(
    request: ReviewWorkbenchRequest,
    sources: tuple[str, ...],
    reasons: list[str],
    started: float,
) -> ReviewWorkbenchResult:
    trace = {
        "operation": "review_workbench",
        "quality_ok": False,
        "low_confidence": True,
        "quality_reasons": list(reasons),
        "trace_warnings": list(reasons),
        "final_citation_count": 0,
    }
    metadata = UseCaseMetadata(
        mode="review_workbench",
        insufficient_evidence=True,
        support_status="insufficient_evidence",
        refusal_reason="no_relevant_evidence",
        warnings=tuple(reasons),
        issues=(ServiceIssue(code="insufficient_evidence", message=_INSUFFICIENT_MESSAGE, severity="info"),),
        timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
        workflow_trace=trace,
    )
    return ReviewWorkbenchResult(
        answer_markdown=_INSUFFICIENT_MESSAGE,
        payload={
            "schema_name": _REVIEW_SCHEMA_NAME,
            "topic": request.topic,
            "sources": list(sources),
            "overview": "",
            "table": [],
            "takeaways": [],
            "citation_count": 0,
            "insufficient_evidence": True,
        },
        citations=[],
        metadata=metadata,
    )
