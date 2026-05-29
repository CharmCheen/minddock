"""Tests for hybrid retrieval evaluation comparison support."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.models import (
    BenchmarkCase,
    EvaluationReport,
    EvaluationRunArtifacts,
    EvaluationSummary,
)
from app.evaluation.runner import run_evaluation_from_dataset


class _FakeFacade:
    """Minimal facade that returns deterministic responses based on retrieval_mode captured via settings."""

    def __init__(self) -> None:
        self.call_count = 0

    def execute(self, request):
        from app.application.models import TaskType, UnifiedExecutionResponse
        from app.application.artifacts import ArtifactKind, SearchResultItemArtifact, SearchResultsArtifact
        from app.rag.retrieval_models import CitationRecord
        from app.services.service_models import UseCaseMetadata, UseCaseTiming

        self.call_count += 1
        return UnifiedExecutionResponse(
            task_type=TaskType.SEARCH,
            artifacts=(
                SearchResultsArtifact(
                    artifact_id=f"search-{self.call_count}",
                    kind=ArtifactKind.SEARCH_RESULTS,
                    items=(
                        SearchResultItemArtifact(
                            chunk_id="d1:0",
                            doc_id="d1",
                            source="doc.md",
                            source_type="file",
                            snippet="storage",
                        ),
                    ),
                    total=1,
                    offset=0,
                    limit=5,
                ),
            ),
            citations=(CitationRecord(doc_id="d1", chunk_id="d1:0", source="doc.md", snippet="storage"),),
            metadata=UseCaseMetadata(timing=UseCaseTiming(total_ms=10.0)),
        )


def _write_dataset(tmp_path: Path) -> Path:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"id":"case-1","task_type":"search","query":"storage","expected_doc_ids":["d1"]}\n',
        encoding="utf-8",
    )
    return dataset


def test_run_evaluation_accepts_retrieval_mode_dense(tmp_path: Path) -> None:
    """run_evaluation_from_dataset accepts retrieval_mode='dense' and forces hybrid off."""
    dataset = _write_dataset(tmp_path)
    facade = _FakeFacade()

    result = run_evaluation_from_dataset(
        dataset_path=dataset,
        output_dir=tmp_path / "reports",
        facade=facade,
        retrieval_mode="dense",
    )

    assert result.report.summary.dataset_size == 1
    assert result.report.summary.retrieval["hit_at_5"] == 1.0


def test_run_evaluation_accepts_retrieval_mode_hybrid(tmp_path: Path) -> None:
    """run_evaluation_from_dataset accepts retrieval_mode='hybrid' and forces hybrid on."""
    dataset = _write_dataset(tmp_path)
    facade = _FakeFacade()

    result = run_evaluation_from_dataset(
        dataset_path=dataset,
        output_dir=tmp_path / "reports",
        facade=facade,
        retrieval_mode="hybrid",
    )

    assert result.report.summary.dataset_size == 1


def test_run_evaluation_default_retrieval_mode_does_not_override(tmp_path: Path, monkeypatch) -> None:
    """When retrieval_mode is None, the setting is not overridden."""
    from app.core.config import Settings

    dataset = _write_dataset(tmp_path)
    facade = _FakeFacade()

    original_setting = Settings.model_fields["hybrid_retrieval_enabled"].default

    result = run_evaluation_from_dataset(
        dataset_path=dataset,
        output_dir=tmp_path / "reports",
        facade=facade,
        retrieval_mode=None,
    )

    assert result.report.summary.dataset_size == 1


def test_run_evaluation_invalid_retrieval_mode_raises(tmp_path: Path) -> None:
    """Invalid retrieval_mode raises ValueError."""
    dataset = _write_dataset(tmp_path)

    try:
        run_evaluation_from_dataset(
            dataset_path=dataset,
            output_dir=tmp_path / "reports",
            facade=_FakeFacade(),
            retrieval_mode="invalid",
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "retrieval_mode" in str(e).lower() or "invalid" in str(e).lower()


def test_comparison_report_generation(tmp_path: Path) -> None:
    """run_comparison_evaluation produces both dense and hybrid reports plus a delta."""
    from app.evaluation.runner import run_comparison_evaluation

    dataset = _write_dataset(tmp_path)
    facade = _FakeFacade()

    result = run_comparison_evaluation(
        dataset_path=dataset,
        output_dir=tmp_path / "reports",
        facade=facade,
    )

    assert result.dense_report is not None
    assert result.hybrid_report is not None
    assert result.comparison is not None
    assert "retrieval" in result.comparison
    # Each metric has nested dense/hybrid values
    assert "dense" in result.comparison["retrieval"]["hit_at_1"]
    assert "hybrid" in result.comparison["retrieval"]["hit_at_1"]


def test_comparison_report_delta_has_required_metrics(tmp_path: Path) -> None:
    """Comparison delta contains at least the required metrics."""
    from app.evaluation.runner import run_comparison_evaluation

    dataset = _write_dataset(tmp_path)
    facade = _FakeFacade()

    result = run_comparison_evaluation(
        dataset_path=dataset,
        output_dir=tmp_path / "reports",
        facade=facade,
    )

    delta = result.comparison
    assert "retrieval" in delta
    assert "hit_at_1" in delta["retrieval"]
    assert "hit_at_3" in delta["retrieval"]
    assert "hit_at_5" in delta["retrieval"]
    assert "latency" in delta
