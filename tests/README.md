# Baseline Tests

The MindDock shared baseline is verified by the following stable test set.

## Run baseline locally

```bash
python scripts/run_ci_baseline.py
```

This script runs all baseline tests and is also the command used by the CI
workflow (`.github/workflows/ci-baseline.yml`).

## What is covered

| Coverage | Files |
|---|---|
| Contract master/slave relations | `tests/contract/test_contracts.py` |
| Unified execution / freshness / artifact-first | `tests/unit/test_application_orchestrators.py` |
| Demo entry-point consistency | `tests/unit/test_demo.py` |
| Evaluation / replay acceptance surface | `tests/unit/test_evaluation.py` |
| Run control / replay boundary | `tests/unit/test_run_control.py` |
| API integration baseline (stable subset) | `tests/integration/test_api_routes.py` (46/47 tests; 1 excluded due to `langchain_chroma` env dependency) |

## Benchmark

Benchmark entry (first version):

```bash
python -m app.demo evaluate --dataset eval/benchmark/sample_eval_set.jsonl
```

`scripts/evaluate_rag.py` is a thin alias for the same command. Reports are written to `data/eval/`.
