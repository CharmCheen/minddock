"""Evaluation runner that reuses MindDock's existing unified execution chain."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from app.application import CitationPolicy, OutputMode, RetrievalOptions, SkillPolicy, TaskType, UnifiedExecutionRequest, get_frontend_facade
from app.application.models import UnifiedExecutionResponse
from app.evaluation.datasets import load_benchmark_dataset
from app.evaluation.metrics import (
    evaluate_citation_consistency,
    evaluate_retrieval,
    extract_retrieval_references,
    summarize_results,
)
from app.evaluation.models import BenchmarkCase, EvaluationCaseResult, EvaluationReport, EvaluationRunArtifacts
from app.evaluation.reporting import write_report_files


def run_evaluation_from_dataset(
    dataset_path: str | Path,
    *,
    output_dir: str | Path = "data/eval",
    task_types: tuple[str, ...] = (),
    facade=None,
) -> EvaluationRunArtifacts:
    """Load a dataset, run all requested cases, and persist JSON/Markdown reports."""

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
        dataset_stem=Path(dataset_path).stem,
    )
    return EvaluationRunArtifacts(
        report=report,
        json_path=json_path,
        markdown_path=markdown_path,
    )


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
    failure_reasons = _build_failure_reasons(retrieval, citation)
    return EvaluationCaseResult(
        case_id=case.id,
        task_type=case.task_type,
        query=case.query,
        top_k=case.top_k,
        retrieval=retrieval,
        citation=citation,
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


def _build_failure_reasons(retrieval, citation) -> tuple[str, ...]:
    reasons: list[str] = []
    if not retrieval.hit_at_5:
        reasons.append("retrieval_miss@5")
    if not citation.structure_consistent:
        reasons.append("citation_structure_mismatch")
    if citation.expected_source_consistent is False:
        reasons.append("citation_expected_source_miss")
    return tuple(reasons)
