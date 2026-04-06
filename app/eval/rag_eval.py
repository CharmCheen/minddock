"""Lightweight RAG evaluation helpers for local experiments."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.services.search_service import SearchService
from app.services.summarize_service import SummarizeService


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_source: str
    top_k: int = 3


DEFAULT_CASES = [
    EvalCase(
        query="Where does MindDock store document chunks and metadata?",
        expected_source="example.md",
        top_k=3,
    ),
    EvalCase(
        query="Summarize how MindDock stores chunks and metadata",
        expected_source="example.md",
        top_k=3,
    ),
]


def evaluate_cases(cases: list[EvalCase] | None = None) -> dict[str, object]:
    search_service = SearchService()
    summarize_service = SummarizeService()
    eval_cases = cases or DEFAULT_CASES

    rows: list[dict[str, object]] = []
    hit_count = 0
    for case in eval_cases:
        start = time.perf_counter()
        search_result = search_service.search(query=case.query, top_k=case.top_k)
        search_ms = round((time.perf_counter() - start) * 1000, 2)

        top_sources = [str(hit.chunk.source) for hit in search_result.hits]
        top_hit_match = case.expected_source in top_sources
        if top_hit_match:
            hit_count += 1

        start = time.perf_counter()
        summary_result = summarize_service.summarize(topic=case.query, top_k=case.top_k)
        summary_ms = round((time.perf_counter() - start) * 1000, 2)

        citation_complete = all(
            citation.doc_id and citation.chunk_id and citation.source
            for citation in summary_result.citations
        )
        rows.append(
            {
                "query": case.query,
                "expected_source": case.expected_source,
                "top_sources": top_sources,
                "top_hit_match": top_hit_match,
                "search_latency_ms": search_ms,
                "summary_latency_ms": summary_ms,
                "citation_complete": citation_complete,
                "retrieved_count": summary_result.metadata.retrieved_count,
                "insufficient_evidence": summary_result.metadata.insufficient_evidence,
                "search_total_ms": search_result.metadata.timing.total_ms,
                "summary_total_ms": summary_result.metadata.timing.total_ms,
            }
        )

    return {
        "cases": rows,
        "summary": {
            "case_count": len(eval_cases),
            "top_hit_rate": round(hit_count / max(len(eval_cases), 1), 3),
            "citation_complete_rate": round(
                sum(1 for row in rows if row["citation_complete"]) / max(len(rows), 1),
                3,
            ),
            "avg_search_latency_ms": round(sum(row["search_latency_ms"] for row in rows) / max(len(rows), 1), 2),
            "avg_summary_latency_ms": round(sum(row["summary_latency_ms"] for row in rows) / max(len(rows), 1), 2),
        },
    }


def write_report(report: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
