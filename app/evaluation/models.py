"""Stable data models for MindDock evaluation workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

TaskTypeLiteral = Literal["search", "chat", "compare"]


@dataclass(frozen=True)
class BenchmarkCase:
    """One benchmark case loaded from a local JSONL dataset."""

    id: str
    task_type: TaskTypeLiteral
    query: str
    expected_doc_ids: tuple[str, ...] = ()
    expected_chunk_ids: tuple[str, ...] = ()
    expected_citation_doc_ids: tuple[str, ...] = ()
    notes: str | None = None
    top_k: int = 5

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkCase":
        case_id = str(payload.get("id", "")).strip()
        task_type = str(payload.get("task_type", "")).strip()
        query = str(payload.get("query", "")).strip()
        if not case_id:
            raise ValueError("Benchmark case requires a non-empty 'id'.")
        if task_type not in {"search", "chat", "compare"}:
            raise ValueError(f"Benchmark case '{case_id}' has unsupported task_type '{task_type}'.")
        if not query:
            raise ValueError(f"Benchmark case '{case_id}' requires a non-empty 'query'.")

        return cls(
            id=case_id,
            task_type=task_type,  # type: ignore[arg-type]
            query=query,
            expected_doc_ids=_normalize_str_list(payload.get("expected_doc_ids")),
            expected_chunk_ids=_normalize_str_list(payload.get("expected_chunk_ids")),
            expected_citation_doc_ids=_normalize_str_list(payload.get("expected_citation_doc_ids")),
            notes=_normalize_optional_text(payload.get("notes")),
            top_k=_normalize_top_k(payload.get("top_k")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "query": self.query,
            "expected_doc_ids": list(self.expected_doc_ids),
            "expected_chunk_ids": list(self.expected_chunk_ids),
            "expected_citation_doc_ids": list(self.expected_citation_doc_ids),
            "notes": self.notes,
            "top_k": self.top_k,
        }


@dataclass(frozen=True)
class RetrievalReference:
    """Observed retrieval/evidence reference surfaced by a task response."""

    doc_id: str
    chunk_id: str
    source: str
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalEvaluation:
    """Retrieval hit results for one benchmark case."""

    match_basis: str
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    observed_doc_ids: tuple[str, ...] = ()
    observed_chunk_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_basis": self.match_basis,
            "hit_at_1": self.hit_at_1,
            "hit_at_3": self.hit_at_3,
            "hit_at_5": self.hit_at_5,
            "observed_doc_ids": list(self.observed_doc_ids),
            "observed_chunk_ids": list(self.observed_chunk_ids),
        }


@dataclass(frozen=True)
class CitationConsistencyEvaluation:
    """Deterministic citation consistency checks for one case."""

    structure_consistent: bool
    expected_source_consistent: bool | None
    overall_consistent: bool
    citation_count: int
    citation_doc_ids: tuple[str, ...] = ()
    dangling_citation_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "structure_consistent": self.structure_consistent,
            "expected_source_consistent": self.expected_source_consistent,
            "overall_consistent": self.overall_consistent,
            "citation_count": self.citation_count,
            "citation_doc_ids": list(self.citation_doc_ids),
            "dangling_citation_keys": list(self.dangling_citation_keys),
        }


@dataclass(frozen=True)
class EvaluationCaseResult:
    """Full execution outcome and metrics for one benchmark case."""

    case_id: str
    task_type: TaskTypeLiteral
    query: str
    top_k: int
    retrieval: RetrievalEvaluation
    citation: CitationConsistencyEvaluation
    latency_ms: float
    insufficient_evidence: bool
    response_preview: str
    warnings: tuple[str, ...] = ()
    failure_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "task_type": self.task_type,
            "query": self.query,
            "top_k": self.top_k,
            "retrieval": self.retrieval.to_dict(),
            "citation": self.citation.to_dict(),
            "latency_ms": self.latency_ms,
            "insufficient_evidence": self.insufficient_evidence,
            "response_preview": self.response_preview,
            "warnings": list(self.warnings),
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True)
class LatencySummary:
    """Aggregated latency statistics."""

    avg_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationSummary:
    """Dataset-level aggregated metrics."""

    dataset_size: int
    task_counts: dict[str, int]
    retrieval: dict[str, float]
    citation: dict[str, float | int | None]
    latency: dict[str, Any]
    failed_case_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationReport:
    """Serializable report for one benchmark run."""

    dataset_path: str
    generated_at: str
    cases: tuple[BenchmarkCase, ...]
    results: tuple[EvaluationCaseResult, ...]
    summary: EvaluationSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "generated_at": self.generated_at,
            "cases": [case.to_dict() for case in self.cases],
            "results": [result.to_dict() for result in self.results],
            "summary": self.summary.to_dict(),
        }


@dataclass(frozen=True)
class EvaluationRunArtifacts:
    """Filesystem outputs written for one evaluation run."""

    report: EvaluationReport
    json_path: str
    markdown_path: str


def _normalize_str_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise ValueError("Expected a string or string list.")
    return tuple(str(item).strip() for item in items if str(item).strip())


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_top_k(value: Any) -> int:
    if value in (None, ""):
        return 5
    normalized = int(value)
    if normalized <= 0:
        raise ValueError("Benchmark case 'top_k' must be positive.")
    return normalized
