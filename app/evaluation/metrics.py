"""Deterministic evaluation metrics for retrieval, citation consistency, and latency."""

from __future__ import annotations

from collections import Counter, defaultdict

from app.application.artifacts import ArtifactMapper
from app.application.models import TaskType, UnifiedExecutionResponse
from app.evaluation.models import (
    BenchmarkCase,
    CitationConsistencyEvaluation,
    EvaluationCaseResult,
    EvaluationSummary,
    LatencySummary,
    RetrievalEvaluation,
    RetrievalReference,
)


def _extract_compare_evidence_keys_from_artifact(response: UnifiedExecutionResponse) -> list[tuple[str, str]]:
    """Extract (doc_id, chunk_id) keys from compare.v1 artifact data, or return empty."""
    artifact = ArtifactMapper.first_compare_artifact(response.artifacts)
    if artifact is None:
        return []
    data = artifact.data
    keys: list[tuple[str, str]] = []
    for point in (*data.get("common_points", []), *data.get("differences", []), *data.get("conflicts", [])):
        for ev in (*point.get("left_evidence", []), *point.get("right_evidence", [])):
            keys.append((str(ev.get("doc_id", "")), str(ev.get("chunk_id", ""))))
    return keys


def _extract_compare_evidence_keys_from_top_level(response: UnifiedExecutionResponse) -> list[tuple[str, str]]:
    """Extract (doc_id, chunk_id) keys from top-level compare_result, or return empty."""
    if response.compare_result is None:
        return []
    keys: list[tuple[str, str]] = []
    for point in (*response.compare_result.common_points, *response.compare_result.differences, *response.compare_result.conflicts):
        for ev in (*point.left_evidence, *point.right_evidence):
            keys.append((ev.doc_id, ev.chunk_id))
    return keys


def _build_ordered_retrieval_references(keys: list[tuple[str, str]]) -> list[RetrievalReference]:
    """Build ordered RetrievalReference list from deduplicated (doc_id, chunk_id) keys."""
    seen: set[tuple[str, str]] = set()
    ordered: list[RetrievalReference] = []
    for doc_id, chunk_id in keys:
        key = (doc_id, chunk_id)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(RetrievalReference(doc_id=doc_id, chunk_id=chunk_id, source="", rank=len(ordered) + 1))
    return ordered


def extract_retrieval_references(response: UnifiedExecutionResponse) -> list[RetrievalReference]:
    """Extract ordered retrieval/evidence references from a unified response.

    Priority:
    - search:  SearchResultsArtifact
    - chat/summarize: grounded_answer.evidence
    - compare: compare.v1 structured artifact (primary), top-level compare_result (fallback)
    - citations: only as final fallback for citation consistency input, not primary retrieval source
    """

    search_results = ArtifactMapper.first_search_results(response.artifacts)
    if search_results is not None:
        return [
            RetrievalReference(
                doc_id=item.doc_id,
                chunk_id=item.chunk_id,
                source=item.source,
                rank=index,
            )
            for index, item in enumerate(search_results.items, start=1)
        ]

    if response.grounded_answer is not None and response.grounded_answer.evidence:
        return [
            RetrievalReference(
                doc_id=item.doc_id,
                chunk_id=item.chunk_id,
                source=item.source,
                rank=index,
            )
            for index, item in enumerate(response.grounded_answer.evidence, start=1)
        ]

    if response.task_type == TaskType.COMPARE:
        artifact_keys = _extract_compare_evidence_keys_from_artifact(response)
        if artifact_keys:
            return _build_ordered_retrieval_references(artifact_keys)
        top_level_keys = _extract_compare_evidence_keys_from_top_level(response)
        if top_level_keys:
            return _build_ordered_retrieval_references(top_level_keys)
        return []

    seen: set[tuple[str, str]] = set()
    ordered: list[RetrievalReference] = []
    for citation in response.citations:
        key = (citation.doc_id, citation.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(
            RetrievalReference(
                doc_id=citation.doc_id,
                chunk_id=citation.chunk_id,
                source=citation.source,
                rank=len(ordered) + 1,
            )
        )
    return ordered


def evaluate_retrieval(case: BenchmarkCase, references: list[RetrievalReference]) -> RetrievalEvaluation:
    """Compute hit@k metrics for one case."""

    match_basis = "chunk" if case.expected_chunk_ids else "doc"
    observed_doc_ids = tuple(reference.doc_id for reference in references if reference.doc_id)
    observed_chunk_ids = tuple(reference.chunk_id for reference in references if reference.chunk_id)

    def hit_within(limit: int) -> bool:
        top_refs = references[:limit]
        if case.expected_chunk_ids:
            expected = set(case.expected_chunk_ids)
            return any(reference.chunk_id in expected for reference in top_refs)
        expected = set(case.expected_doc_ids)
        return any(reference.doc_id in expected for reference in top_refs)

    return RetrievalEvaluation(
        match_basis=match_basis,
        hit_at_1=hit_within(1),
        hit_at_3=hit_within(3),
        hit_at_5=hit_within(5),
        observed_doc_ids=observed_doc_ids,
        observed_chunk_ids=observed_chunk_ids,
    )


def evaluate_citation_consistency(
    case: BenchmarkCase,
    response: UnifiedExecutionResponse,
    references: list[RetrievalReference],
) -> CitationConsistencyEvaluation:
    """Check whether citations map to surfaced evidence and expected sources.

    For compare task: reads compare.v1 artifact first (primary), top-level compare_result (fallback).
    citations list is only used as citation consistency input, not as retrieval truth source.
    """

    valid_keys = {(reference.doc_id, reference.chunk_id) for reference in references}
    if response.grounded_answer is not None:
        valid_keys.update((item.doc_id, item.chunk_id) for item in response.grounded_answer.evidence)
    if response.task_type == TaskType.COMPARE:
        artifact_keys = _extract_compare_evidence_keys_from_artifact(response)
        if artifact_keys:
            valid_keys.update(artifact_keys)
        else:
            valid_keys.update(_extract_compare_evidence_keys_from_top_level(response))
    elif response.compare_result is not None:
        for point in (*response.compare_result.common_points, *response.compare_result.differences, *response.compare_result.conflicts):
            valid_keys.update((item.doc_id, item.chunk_id) for item in point.left_evidence)
            valid_keys.update((item.doc_id, item.chunk_id) for item in point.right_evidence)

    dangling = tuple(
        f"{citation.doc_id}:{citation.chunk_id}"
        for citation in response.citations
        if (citation.doc_id, citation.chunk_id) not in valid_keys
    )
    citation_doc_ids = tuple(dict.fromkeys(citation.doc_id for citation in response.citations if citation.doc_id))
    structure_consistent = not dangling

    expected_source_consistent: bool | None = None
    if case.expected_citation_doc_ids:
        expected = set(case.expected_citation_doc_ids)
        expected_source_consistent = expected.issubset(set(citation_doc_ids))

    overall_consistent = structure_consistent and expected_source_consistent is not False
    return CitationConsistencyEvaluation(
        structure_consistent=structure_consistent,
        expected_source_consistent=expected_source_consistent,
        overall_consistent=overall_consistent,
        citation_count=len(response.citations),
        citation_doc_ids=citation_doc_ids,
        dangling_citation_keys=dangling,
    )


def summarize_latencies(latency_values_ms: list[float]) -> LatencySummary:
    """Aggregate latency values into avg/p50/p95/max stats."""

    if not latency_values_ms:
        return LatencySummary(avg_ms=0.0, p50_ms=0.0, p95_ms=0.0, max_ms=0.0, sample_count=0)
    ordered = sorted(float(value) for value in latency_values_ms)
    avg_ms = round(sum(ordered) / len(ordered), 2)
    return LatencySummary(
        avg_ms=avg_ms,
        p50_ms=round(_percentile(ordered, 50), 2),
        p95_ms=round(_percentile(ordered, 95), 2),
        max_ms=round(ordered[-1], 2),
        sample_count=len(ordered),
    )


def summarize_results(results: list[EvaluationCaseResult]) -> EvaluationSummary:
    """Build dataset-level summary metrics from per-case results."""

    total = len(results)
    task_counts = dict(Counter(result.task_type for result in results))
    retrieval = {
        "hit_at_1": _safe_rate(sum(1 for result in results if result.retrieval.hit_at_1), total),
        "hit_at_3": _safe_rate(sum(1 for result in results if result.retrieval.hit_at_3), total),
        "hit_at_5": _safe_rate(sum(1 for result in results if result.retrieval.hit_at_5), total),
    }

    expected_cases = [result for result in results if result.citation.expected_source_consistent is not None]
    citation = {
        "overall_consistency_rate": _safe_rate(sum(1 for result in results if result.citation.overall_consistent), total),
        "structure_consistency_rate": _safe_rate(sum(1 for result in results if result.citation.structure_consistent), total),
        "expected_source_consistency_rate": (
            _safe_rate(sum(1 for result in expected_cases if result.citation.expected_source_consistent), len(expected_cases))
            if expected_cases
            else None
        ),
        "expected_source_case_count": len(expected_cases),
    }

    by_task: dict[str, list[float]] = defaultdict(list)
    for result in results:
        by_task[result.task_type].append(result.latency_ms)
    latency = {
        "overall": summarize_latencies([result.latency_ms for result in results]).to_dict(),
        "by_task_type": {task_type: summarize_latencies(values).to_dict() for task_type, values in sorted(by_task.items())},
    }

    failed_case_count = sum(1 for result in results if result.failure_reasons)
    return EvaluationSummary(
        dataset_size=total,
        task_counts=task_counts,
        retrieval=retrieval,
        citation=citation,
        latency=latency,
        failed_case_count=failed_case_count,
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (percentile / 100.0)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return lower + (upper - lower) * fraction
