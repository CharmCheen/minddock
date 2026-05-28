# MindDock Evaluation Baseline

## 1. Purpose

The evaluation baseline provides a reproducible set of inputs and metrics for measuring MindDock's RAG quality. Its purpose is to establish a **smoke-test baseline** — not to claim optimal performance.

This baseline enables:
- Detecting quality regressions across commits
- Comparing different retrieval/rerank/generation configurations
- Tracking improvement over time with concrete numbers

It does **not**:
- Claim production-grade RAG quality
- Replace a real user knowledge base
- Provide statistically significant conclusions (the dataset is too small)

## 2. Fixture Dataset

`eval/benchmark/fixtures/` contains four minimal, deterministic documents:

| File | Topic | Covers |
|------|-------|--------|
| `example.md` | Project overview | Storage, citations, workflow trace |
| `architecture.md` | System architecture | Layers, orchestrators, execution plan |
| `rag_pipeline.md` | RAG pipeline | Chunking, embedding, retrieval, rerank, compression, evidence |
| `api_usage.md` | API and runtime | Endpoints, runtime config, mock runtime, fail-closed behavior |

These fixtures are designed to be:
- Small (~500-800 words each)
- Stable (changes break golden set alignment)
- Privacy-free (no user data)
- Self-contained (no external dependencies)

Doc IDs are deterministic: `sha1(relative_path)`.

## 3. Golden Set

`eval/benchmark/golden_eval_set.jsonl` contains 19 cases:

| Task Type | Count | IE Cases | Fixture Coverage |
|-----------|-------|----------|-----------------|
| search | 8 | 0 | All map to fixtures |
| chat | 8 | 4 (IE) | 4 supported map to fixtures |
| compare | 3 | 0 | All map to 2 fixtures each |

Insufficient-evidence cases test queries that the fixtures **cannot** answer:
- Token rotation strategy for authentication
- Horizontal scaling across servers
- ML model training pipeline
- Database migration strategy

## 4. Metrics

The evaluator computes four metric categories:

### Retrieval
- `hit@1`, `hit@3`, `hit@5` — whether expected doc/chunk appears in top-K results
- Computed by `evaluate_retrieval()`

### Citation Consistency
- `structure_consistent` — no dangling citations (all citations map to evidence)
- `expected_source_consistent` — expected doc_ids appear in citation list
- `overall_consistent` — both structure and expected source pass
- Computed by `evaluate_citation_consistency()`

### Insufficient Evidence Detection
- `accuracy` — overall correctness of IE judgment
- `refusal_precision` — correct refusals / expected refusals
- `non_refusal_accuracy` — correct non-refusals / expected non-refusals
- Computed by `evaluate_insufficient_evidence()`

### Latency
- `avg_ms`, `p50_ms`, `p95_ms`, `max_ms` — per-case and aggregate
- Computed by `summarize_latencies()`

## 5. How To Run In Full Environment

```bash
# Install dependencies
pip install -e ".[dev]"

# Run static fixture tests (no Chroma/LLM needed)
pytest tests/unit/test_evaluation_fixtures.py -v

# Run evaluation unit tests (uses FakeFacade, no Chroma/LLM needed)
pytest tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v

# Ingest fixtures into knowledge base
# Option A: set KB_DIR env var
KB_DIR=eval/benchmark/fixtures python -c "from app.rag.ingest import ingest; ingest(rebuild=True)"

# Option B: use start.bat with WATCH_PATH pointing to fixtures
# (need to confirm exact command in full environment)

# Run golden evaluation
python scripts/evaluate_rag.py \
  --dataset eval/benchmark/golden_eval_set.jsonl \
  --output-dir data/eval

# Run sample evaluation
python scripts/evaluate_rag.py \
  --dataset eval/benchmark/sample_eval_set.jsonl \
  --output-dir data/eval

# View reports
cat data/eval/golden_eval_set_evaluation_report.md
cat data/eval/sample_eval_set_evaluation_report.md
```

**Note:** The exact ingest command for fixtures needs to be confirmed in a full environment. The `KB_DIR` approach assumes the ingest function reads from `settings.kb_dir`.

## 6. Known Limitations

- **Mac environment:** No tests or evaluations have been run. All changes are static.
- **No Chroma/embedding verification:** The fixture ingest path has not been tested against a real Chroma instance.
- **No LLM verification:** The generation layer has not been tested with a real LLM runtime.
- **No cross-encoder reranker:** The reranker is a heuristic stub.
- **No hybrid retrieval:** BM25+RRF is disabled by default.
- **No NLI citation verification:** Citations are derived from retrieved chunks, not verified by entailment.
- **Small dataset:** 19 cases is a smoke baseline, not a statistically significant benchmark.
- **Chunk ID fragility:** `expected_chunk_ids` in the golden set depend on the exact chunking behavior of the splitter. Changes to chunk size, overlap, or tokenizer may invalidate these.

## 7. Next Step

**Do not enter P1 (hybrid retrieval / reranker) yet.** The immediate next step is:

1. Run `pytest tests/unit/test_evaluation_fixtures.py -v` in full environment
2. Run `pytest tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v`
3. Ingest fixtures: `KB_DIR=eval/benchmark/fixtures python -c "from app.rag.ingest import ingest; ingest(rebuild=True)"`
4. Run `python scripts/evaluate_rag.py --dataset eval/benchmark/golden_eval_set.jsonl --output-dir data/eval`
5. Record baseline metrics (retrieval hit@k, citation consistency, IE accuracy, latency)
6. Only then decide whether hybrid retrieval or reranker is the next priority

## 8. Doc ID Stability

`doc_id` is generated as `sha1(source)` where `source` is the relative file path from the knowledge base directory. This means:

- Renaming a fixture file changes its doc_id
- Moving a fixture file to a subdirectory changes its doc_id
- The golden set must be updated if fixture filenames change

This is by design — the evaluation should be tied to specific, known documents. If you need to test with different documents, create a new golden set with the corresponding doc_ids.
