"""Unit tests for the legacy evaluation wrapper."""

from app.eval.rag_eval import evaluate_cases
from app.evaluation.models import EvaluationReport, EvaluationRunArtifacts, EvaluationSummary


def test_legacy_evaluate_cases_delegates_to_new_module(monkeypatch) -> None:
    fake_run = EvaluationRunArtifacts(
        report=EvaluationReport(
            dataset_path="eval/benchmark/sample_eval_set.jsonl",
            generated_at="2026-04-07T00:00:00+00:00",
            cases=(),
            results=(),
            summary=EvaluationSummary(
                dataset_size=1,
                task_counts={"search": 1},
                retrieval={"hit_at_1": 1.0, "hit_at_3": 1.0, "hit_at_5": 1.0},
                citation={
                    "overall_consistency_rate": 1.0,
                    "structure_consistency_rate": 1.0,
                    "expected_source_consistency_rate": 1.0,
                    "expected_source_case_count": 1,
                },
                latency={
                    "overall": {"avg_ms": 10.0, "p50_ms": 10.0, "p95_ms": 10.0, "max_ms": 10.0, "sample_count": 1},
                    "by_task_type": {},
                },
                failed_case_count=0,
            ),
        ),
        json_path="data/eval/report.json",
        markdown_path="data/eval/report.md",
    )
    monkeypatch.setattr("app.eval.rag_eval.run_evaluation_from_dataset", lambda dataset_path: fake_run)

    report = evaluate_cases()

    assert report["summary"]["dataset_size"] == 1
    assert report["summary"]["retrieval"]["hit_at_1"] == 1.0
