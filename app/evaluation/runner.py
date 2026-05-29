"""Evaluation runner that reuses MindDock's existing unified execution chain."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.application import CitationPolicy, OutputMode, RetrievalOptions, SkillPolicy, TaskType, UnifiedExecutionRequest, get_frontend_facade
from app.application.models import UnifiedExecutionResponse
from app.evaluation.datasets import load_benchmark_dataset
from app.evaluation.metrics import (
    evaluate_citation_consistency,
    evaluate_insufficient_evidence,
    evaluate_retrieval,
    extract_retrieval_references,
    summarize_results,
)
from app.evaluation.models import BenchmarkCase, EvaluationCaseResult, EvaluationReport, EvaluationRunArtifacts
from app.evaluation.reporting import write_report_files

_VALID_RETRIEVAL_MODES = ("dense", "hybrid")


@contextmanager
def _retrieval_mode_override(mode: str | None):
    """Temporarily override hybrid_retrieval_enabled in settings."""
    if mode is None:
        yield
        return

    if mode not in _VALID_RETRIEVAL_MODES:
        raise ValueError(f"Invalid retrieval_mode '{mode}'. Must be one of: {_VALID_RETRIEVAL_MODES}")

    from app.core.config import get_settings

    settings = get_settings()
    desired = mode == "hybrid"
    original = settings.hybrid_retrieval_enabled
    if original == desired:
        yield
        return

    settings.hybrid_retrieval_enabled = desired
    try:
        yield
    finally:
        settings.hybrid_retrieval_enabled = original


def run_evaluation_from_dataset(
    dataset_path: str | Path,
    *,
    output_dir: str | Path = "data/eval",
    task_types: tuple[str, ...] = (),
    facade=None,
    retrieval_mode: str | None = None,
) -> EvaluationRunArtifacts:
    """Load a dataset, run all requested cases, and persist JSON/Markdown reports.

    Args:
        retrieval_mode: Override retrieval strategy for this run.
            ``"dense"`` forces dense-only, ``"hybrid"`` forces dense+BM25+RRF.
            ``None`` (default) uses whatever the current settings specify.
    """

    with _retrieval_mode_override(retrieval_mode):
        cases = load_benchmark_dataset(dataset_path)
        filtered_cases = [case for case in cases if not task_types or case.task_type in task_types]
        if not filtered_cases:
            raise ValueError("No benchmark cases matched the requested task-type filter.")

        active_facade = facade or get_frontend_facade()
        results = [run_case(case, facade=active_facade) for case in filtered_cases]
        report = EvaluationReport(
            dataset_path=str(Path(dataset_path)),
            generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            cases=tuple(filtered_cases),
            results=tuple(results),
            summary=summarize_results(results),
        )
        json_path, markdown_path = write_report_files(
            report,
            output_dir=output_dir,
            dataset_stem=_output_stem(Path(dataset_path).stem, retrieval_mode),
        )
        return EvaluationRunArtifacts(
            report=report,
            json_path=json_path,
            markdown_path=markdown_path,
        )


def _output_stem(base_stem: str, retrieval_mode: str | None) -> str:
    if retrieval_mode is None:
        return base_stem
    return f"{base_stem}_{retrieval_mode}"


@dataclass(frozen=True)
class ComparisonEvaluationResult:
    """Result of a dense-vs-hybrid comparison evaluation."""

    dense_report: EvaluationReport
    hybrid_report: EvaluationReport
    comparison: dict[str, Any]
    dense_json_path: str
    dense_markdown_path: str
    hybrid_json_path: str
    hybrid_markdown_path: str


def run_comparison_evaluation(
    dataset_path: str | Path,
    *,
    output_dir: str | Path = "data/eval",
    task_types: tuple[str, ...] = (),
    facade=None,
) -> ComparisonEvaluationResult:
    """Run evaluation in both dense-only and hybrid modes, return delta metrics."""

    dense_result = run_evaluation_from_dataset(
        dataset_path=dataset_path,
        output_dir=output_dir,
        task_types=task_types,
        facade=facade,
        retrieval_mode="dense",
    )
    hybrid_result = run_evaluation_from_dataset(
        dataset_path=dataset_path,
        output_dir=output_dir,
        task_types=task_types,
        facade=facade,
        retrieval_mode="hybrid",
    )
    comparison = _build_comparison_delta(dense_result.report, hybrid_result.report)
    return ComparisonEvaluationResult(
        dense_report=dense_result.report,
        hybrid_report=hybrid_result.report,
        comparison=comparison,
        dense_json_path=dense_result.json_path,
        dense_markdown_path=dense_result.markdown_path,
        hybrid_json_path=hybrid_result.json_path,
        hybrid_markdown_path=hybrid_result.markdown_path,
    )


def _build_comparison_delta(
    dense: EvaluationReport,
    hybrid: EvaluationReport,
) -> dict[str, Any]:
    """Build a comparison delta dict between dense and hybrid reports."""

    def _delta(d: dict[str, Any], h: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in keys:
            d_val = d.get(key)
            h_val = h.get(key)
            result[key] = {"dense": d_val, "hybrid": h_val}
            if isinstance(d_val, (int, float)) and isinstance(h_val, (int, float)):
                result[key]["delta"] = round(h_val - d_val, 6)
        return result

    retrieval_keys = ("hit_at_1", "hit_at_3", "hit_at_5")
    citation_keys = ("overall_consistency_rate", "expected_source_consistency_rate")
    ie_keys = ("accuracy", "non_refusal_accuracy")
    latency_overall_dense = dense.summary.latency.get("overall", {})
    latency_overall_hybrid = hybrid.summary.latency.get("overall", {})

    return {
        "retrieval": _delta(dense.summary.retrieval, hybrid.summary.retrieval, retrieval_keys),
        "citation": _delta(dense.summary.citation, hybrid.summary.citation, citation_keys),
        "insufficient_evidence": _delta(
            dense.summary.insufficient_evidence,
            hybrid.summary.insufficient_evidence,
            ie_keys,
        ),
        "latency": {
            "dense_avg_ms": latency_overall_dense.get("avg_ms"),
            "hybrid_avg_ms": latency_overall_hybrid.get("avg_ms"),
        },
    }


def run_case(case: BenchmarkCase, *, facade) -> EvaluationCaseResult:
    """Execute one benchmark case against the unified frontend facade."""

    request = _build_request(case)
    started = time.perf_counter()
    response = facade.execute(request)
    wall_clock_ms = round((time.perf_counter() - started) * 1000, 2)
    latency_ms = response.metadata.timing.total_ms if response.metadata.timing.total_ms is not None else wall_clock_ms
    references = extract_retrieval_references(response)
    retrieval = evaluate_retrieval(case, references)
    citation = evaluate_citation_consistency(case, response, references)
    ie_eval = evaluate_insufficient_evidence(case, response)
    failure_reasons = _build_failure_reasons(retrieval, citation, ie_eval)
    return EvaluationCaseResult(
        case_id=case.id,
        task_type=case.task_type,
        query=case.query,
        top_k=case.top_k,
        retrieval=retrieval,
        citation=citation,
        insufficient_evidence_eval=ie_eval,
        latency_ms=float(latency_ms),
        insufficient_evidence=response.metadata.insufficient_evidence,
        response_preview=_response_preview(response),
        warnings=tuple(response.metadata.warnings),
        failure_reasons=failure_reasons,
    )


def _build_request(case: BenchmarkCase) -> UnifiedExecutionRequest:
    task_type = TaskType(case.task_type)
    output_mode = OutputMode.STRUCTURED if task_type == TaskType.COMPARE else OutputMode.TEXT
    return UnifiedExecutionRequest(
        task_type=task_type,
        user_input=case.query,
        retrieval=RetrievalOptions(top_k=case.top_k),
        output_mode=output_mode,
        citation_policy=CitationPolicy.PREFERRED,
        skill_policy=SkillPolicy(),
        include_metadata=True,
    )


def _response_preview(response: UnifiedExecutionResponse) -> str:
    preview = response.primary_text().strip()
    if not preview and response.compare_result is not None:
        preview = response.compare_result.support_status.value
    if len(preview) <= 160:
        return preview
    return f"{preview[:157]}..."


def _build_failure_reasons(retrieval, citation, ie_eval) -> tuple[str, ...]:
    reasons: list[str] = []
    if not retrieval.hit_at_5:
        reasons.append("retrieval_miss@5")
    if not citation.structure_consistent:
        reasons.append("citation_structure_mismatch")
    if citation.expected_source_consistent is False:
        reasons.append("citation_expected_source_miss")
    if not ie_eval.correct:
        reasons.append("insufficient_evidence_mismatch")
    return tuple(reasons)
