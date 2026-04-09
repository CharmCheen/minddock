# Evaluation

## Overview

MindDock includes a lightweight local evaluation workflow for local validation and regression.
The current framework focuses on three deterministic metrics:

- retrieval hit rate (`hit@1`, `hit@3`, `hit@5`)
- citation consistency
- latency

The implementation reuses the existing `search / chat / compare` unified execution path and does not introduce a second evidence or citation protocol.

## Benchmark Entry

The recommended benchmark entry point is:

```bash
python -m app.demo evaluate --dataset eval/benchmark/sample_eval_set.jsonl
```

`scripts/evaluate_rag.py` is a thin alias for the same command and can be used interchangeably:

```bash
python scripts/evaluate_rag.py --dataset eval/benchmark/sample_eval_set.jsonl
```

Both commands accept `--output-dir` (default `data/eval`) and `--task-type` filters (`search`, `chat`, `compare`).

The default dataset `eval/benchmark/sample_eval_set.jsonl` is the first-version sample benchmark. It is a small hand-curated set covering search, chat, and compare task types for local validation. Run it to produce a console summary plus JSON and Markdown reports.

## Benchmark Format

Benchmark datasets use JSONL and can be stored under `eval/benchmark/`.
Each line is one case.

Example fields:

```json
{
  "id": "chat_citation_fields",
  "task_type": "chat",
  "query": "What citation fields do chat and summarize responses return?",
  "expected_doc_ids": ["56b97ed9cc7de1ecc311f1ecfd9454276e83842d"],
  "expected_chunk_ids": ["56b97ed9cc7de1ecc311f1ecfd9454276e83842d:1"],
  "expected_citation_doc_ids": ["56b97ed9cc7de1ecc311f1ecfd9454276e83842d"],
  "notes": "Single-document QA grounded in example.md Citations section.",
  "top_k": 5
}
```

Supported fields:

- `id`: unique case id
- `task_type`: `search`, `chat`, or `compare`
- `query`: input query sent to the system
- `expected_doc_ids`: expected source-level targets
- `expected_chunk_ids`: optional expected chunk-level targets
- `expected_citation_doc_ids`: optional expected citation source ids
- `notes`: optional human-readable notes
- `top_k`: optional retrieval depth, default `5`

## Prerequisites

The benchmark requires `langchain-chroma` (which pulls in `chromadb`). Both benchmark entry points (`python -m app.demo evaluate` and `python scripts/evaluate_rag.py`) check for this dependency early and fail with a clear message if it is absent — rather than letting the error surface deep inside a case run.

## How To Run

Make sure MindDock dependencies are installed and the knowledge base has been ingested.

```bash
python -m app.demo evaluate --dataset eval/benchmark/sample_eval_set.jsonl
```

Optional arguments:

- `--output-dir data/eval`
- `--task-type search`
- `--task-type chat`
- `--task-type compare`

The command prints a console summary and writes two files:

- JSON: full machine-readable report
- Markdown: thesis/demo friendly report

## How To Read The Results

The console summary includes:

- dataset size
- task counts
- retrieval `hit@1 / hit@3 / hit@5`
- citation consistency rates
- latency `avg / p50 / p95 / max`

The Markdown report additionally includes:

- per-case summary table
- failed-case list
- per-task latency summary

## Current Scope And Boundaries

- Citation evaluation is deterministic only.
- The current citation checks validate structure consistency and expected-source consistency.
- The framework does not perform semantic answer scoring.
- The framework currently targets `search / chat / compare`.
- `summarize` and workflow-style tasks can be added later with the same dataset format.

## Benchmark Stability

`eval/benchmark/sample_eval_set.jsonl` is the first-version sample benchmark for local validation. It is a small hand-curated set — not a production-grade acceptance test suite. Expected hit rates and citation consistency rates will vary as the knowledge base and retrieval pipeline evolve. Do not treat this dataset as a fixed contract for release gating without first stabilising the failing cases.
