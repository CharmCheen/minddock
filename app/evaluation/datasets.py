"""Benchmark dataset loading for evaluation runs."""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.models import BenchmarkCase


def load_benchmark_dataset(dataset_path: str | Path) -> list[BenchmarkCase]:
    """Load a JSONL benchmark dataset with one case per line."""

    path = Path(dataset_path)
    cases: list[BenchmarkCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            try:
                cases.append(BenchmarkCase.from_dict(payload))
            except ValueError as exc:
                raise ValueError(f"Invalid benchmark case at {path}:{line_number}: {exc}") from exc
    if not cases:
        raise ValueError(f"Benchmark dataset '{path}' did not contain any cases.")
    return cases
