# Evaluation Benchmark Fixtures

This directory contains deterministic fixture documents for MindDock's evaluation baseline.

## Purpose

These fixtures exist so that the golden evaluation dataset (`golden_eval_set.jsonl`) can run against a known, reproducible knowledge base. They are **not** representative of real user knowledge bases — they are minimal, stable documents designed for smoke-testing the evaluation pipeline.

## Documents

| File | Purpose | Covers |
|------|---------|--------|
| `example.md` | Basic project introduction | storage, citations, workflow trace |
| `architecture.md` | System architecture | layers, FrontendFacade, ChatOrchestrator, ExecutionPlan |
| `rag_pipeline.md` | RAG pipeline details | chunking, embedding, retrieval, rerank, compression, evidence |
| `api_usage.md` | API and runtime config | endpoints, runtime provider, mock runtime, fail-closed behavior |

## How To Use

In a full environment with all dependencies installed:

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Ingest fixtures into the knowledge base
#    (point KB_DIR to this fixtures directory)
KB_DIR=eval/benchmark/fixtures python -c "from app.rag.ingest import ingest; ingest(rebuild=True)"

# 3. Run the golden evaluation
python scripts/evaluate_rag.py \
  --dataset eval/benchmark/golden_eval_set.jsonl \
  --output-dir data/eval

# 4. View the report
cat data/eval/golden_eval_set_evaluation_report.md
```

## Important Notes

- These fixtures produce deterministic `doc_id` values based on `sha1(relative_path)`.
- The `golden_eval_set.jsonl` references these `doc_id` values in `expected_doc_ids`.
- If you rename or move these files, the `doc_id` values will change and the golden set will break.
- Do not add private or sensitive data to these fixtures.
- Keep fixture content small and stable — changes may affect chunk indices and evaluation results.

## Doc ID Generation

MindDock generates `doc_id` as `sha1(source)` where `source` is the relative file path from the knowledge base directory. For these fixtures:

| File | Source | Doc ID |
|------|--------|--------|
| `example.md` | `example.md` | `56b97ed9cc7de1ecc311f1ecfd9454276e83842d` |
| `architecture.md` | `architecture.md` | `b82bfe7e81999e992be9158e66e513f1963eb921` |
| `rag_pipeline.md` | `rag_pipeline.md` | `97a1bf3bafb6e15d0bce34346ae13bbe7247000a` |
| `api_usage.md` | `api_usage.md` | `5f791bd9a336667614fb50c3eee8d9cf82026fa4` |
