# Evaluation

## Overview

MindDock now includes a lightweight local evaluation workflow for thesis validation.
The current framework focuses on three deterministic metrics:

- retrieval hit rate (`hit@1`, `hit@3`, `hit@5`)
- citation consistency
- latency

The implementation reuses the existing `search / chat / compare` main path and does not introduce a second evidence or citation protocol.

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

## How To Run

Make sure the normal MindDock runtime dependencies are installed and the knowledge base has been ingested.

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

The `eval/benchmark/sample_eval_set.jsonl` dataset is used as a **development benchmark** for local validation. It is not yet a stable production-grade acceptance test suite. Expected hit rates and citation consistency rates will vary as the knowledge base and retrieval pipeline evolve. Do not treat this dataset as a fixed contract for release gating without first stabilising the failing cases.
