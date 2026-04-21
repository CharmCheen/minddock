"""Backward-compatible wrapper around the newer evaluation module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.evaluation import run_evaluation_from_dataset

DEFAULT_DATASET = Path("eval/benchmark/sample_eval_set.jsonl")


@dataclass(frozen=True)
class EvalCase:
    """Legacy compatibility shell retained for older imports/tests."""

    query: str
    expected_source: str
    top_k: int = 3


def evaluate_cases(cases: list[EvalCase] | None = None) -> dict[str, object]:
    """Run the default dataset evaluation and return a JSON-compatible report."""

    if cases:
        raise ValueError("Custom legacy EvalCase execution is no longer supported; use app.evaluation instead.")
    return run_evaluation_from_dataset(DEFAULT_DATASET).report.to_dict()


def write_report(report: dict[str, object], output_path: Path) -> None:
    """Write a JSON report to disk for legacy callers."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
