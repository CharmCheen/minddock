# P1 Hybrid Retrieval Validation Result

## 1. Branch and Commit

- Branch: `mac-p1-hybrid-retrieval`
- Base: `mac-p0-evaluation-baseline` (commit `32afde4`)
- Date: 2026-05-29

## 2. Baseline Recap (P0)

- Fixture ingest: 4 docs / 26 chunks (from P0 baseline)
- P1 re-ingest: 5 docs / 38 chunks (includes README.md)
- Golden eval: 19 cases total (8 search, 8 chat, 3 compare)
- **Search-only subset used for comparison** (chat/compare require LLM)

P0 baseline metrics (full 19 cases):
| Metric | Value |
| --- | ---: |
| Recall@1 / hit@1 | 21.05% |
| Recall@3 / hit@3 | 42.11% |
| Recall@5 / hit@5 | 42.11% |
| Citation overall consistency | 78.95% |
| Citation source accuracy | 55.56% |
| Insufficient evidence accuracy | 68.42% |

## 3. What Changed

### Code Changes
1. **`app/evaluation/runner.py`** — Added `retrieval_mode` parameter to `run_evaluation_from_dataset()` that overrides `hybrid_retrieval_enabled` setting during evaluation. Added `run_comparison_evaluation()` function and `ComparisonEvaluationResult` dataclass for side-by-side comparison.

2. **`app/evaluation/__init__.py`** — Updated exports to include `ComparisonEvaluationResult` and `run_comparison_evaluation`.

3. **`scripts/evaluate_rag.py`** — Added `--retrieval-mode` CLI argument with choices `dense`, `hybrid`, `compare`. In `compare` mode, runs both evaluations and prints delta.

4. **`tests/unit/test_evaluation_hybrid.py`** — New test file with 6 tests covering retrieval_mode parameter propagation, config override, invalid mode rejection, comparison report generation, and delta structure.

### No Changes Made To
- `app/rag/hybrid_retrieval.py` — Existing BM25+RRF implementation, unchanged
- `app/core/config.py` — Existing Settings, unchanged
- `app/rag/vectorstore.py` — Existing dense retrieval, unchanged
- Frontend, prompts, agent code

## 4. Tests Run

```
tests/unit/test_evaluation_fixtures.py  — 11 passed
tests/unit/test_evaluation.py           — 18 passed
tests/unit/test_rag_eval.py             — 1 passed
tests/unit/test_hybrid_retrieval.py     — 6 passed
tests/unit/test_hybrid_retrieval_edges.py — 7 passed
tests/unit/test_evaluation_hybrid.py    — 6 passed
────────────────────────────────────────
Total: 49 passed, 0 failed
```

Full unit test suite: 919 passed, 53 failed (pre-existing failures in unrelated modules: compare_service, demo, lazy_exports, prompt_registry, skill_catalog, structured_chunker, text_normalization).

## 5. Dense-Only Metrics (search tasks, 8 cases)

| Metric | Value |
| --- | ---: |
| hit@1 | 25.00% |
| hit@3 | 50.00% |
| hit@5 | 50.00% |
| Citation overall consistency | 100.00% |
| IE accuracy | 100.00% |
| Avg latency | 315.13ms |

## 6. Hybrid Metrics (search tasks, 8 cases)

| Metric | Value |
| --- | ---: |
| hit@1 | 12.50% |
| hit@3 | 37.50% |
| hit@5 | 50.00% |
| Citation overall consistency | 100.00% |
| IE accuracy | 100.00% |
| Avg latency | 302.12ms |

## 7. Metric Delta

| Metric | Dense | Hybrid | Delta |
| --- | ---: | ---: | ---: |
| hit@1 | 25.00% | 12.50% | **-12.50%** |
| hit@3 | 50.00% | 37.50% | **-12.50%** |
| hit@5 | 50.00% | 50.00% | 0.00% |
| Citation overall | 100.00% | 100.00% | 0.00% |
| IE accuracy | 100.00% | 100.00% | 0.00% |
| Avg latency | 315.13ms | 302.12ms | -13.01ms |

## 8. Failed Cases

### Cases where hybrid degraded vs dense:

| Case | Dense hit@1/3/5 | Hybrid hit@1/3/5 | Root Cause |
| --- | --- | --- | --- |
| `search_storage_chroma` | N/Y/Y | N/N/Y | RRF promoted README.md chunk above example.md chunk at rank 3 |
| `search_retrieval_flow` | Y/Y/Y | N/Y/Y | RRF promoted `rag_pipeline.md:2` (in both dense+BM25) over `rag_pipeline.md:3` (dense-only, expected chunk) |

### Cases unchanged (still failing):
- `search_extension_points` — Both miss (expected doc not in top-5)
- `search_ingest_endpoint` — Both miss
- `search_source_lifecycle` — Both miss
- `search_example_citations` — Both miss

### Analysis of Root Cause

The RRF fusion causes **intra-document chunk reordering**. When BM25 returns a different chunk from the same document that dense also returns, RRF boosts it above the chunk that dense ranked higher. Since the evaluation checks `expected_chunk_ids` (exact chunk match), this reordering causes false negatives.

Specifically for `search_retrieval_flow`:
- Dense correctly ranks `rag_pipeline.md:3` at #1 (expected chunk)
- BM25 ranks `rag_pipeline.md:2` at #1 (same doc, different chunk)
- RRF fusion gives `rag_pipeline.md:2` a higher combined score because it appears in **both** lists
- Result: `rag_pipeline.md:3` drops to #3, losing hit@1

**Why BM25 doesn't help on this fixture set:**
1. **Small corpus** (38 chunks, 5 docs) — BM25 IDF signal is weak; many terms appear in most documents
2. **Chunk-level eval** — The eval expects specific chunk_ids, not just doc_ids. RRF reorders chunks within documents.
3. **BM25 promotes term-overlap chunks** — Surface-level lexical matching picks up chunks with common terms (e.g., "retrieval", "query") rather than semantically most relevant ones
4. **No cross-document diversity gain** — With only 5 docs, BM25 doesn't surface novel relevant documents that dense missed

## 9. Remaining Risks

1. **RRF intra-document reordering** — The current RRF implementation doesn't preserve dense ranking for chunks within the same document. A "same-doc tie-break" could fix this.
2. **Small fixture set** — 38 chunks / 5 docs is not representative of production. BM25 may help more with larger, more diverse corpora.
3. **Chat/compare not tested** — These require LLM access. Hybrid might behave differently when the full pipeline (retrieval → generation → citation) is active.
4. **Embedding model dependency** — Results depend on the Qwen3-Embedding-0.6B model. Different embeddings may change the dense-vs-hybrid comparison.

## 10. Can We Proceed To Cross-Encoder Reranker?

**No.** The hybrid retrieval does not improve recall on this fixture set. Before adding a cross-encoder reranker:

1. **Fix RRF intra-document reordering** — Add same-doc tie-break: when two chunks from the same document are ranked, prefer the one that dense ranked higher. This is a minimal change to `_rrf_fuse()` or the result reconstruction in `HybridRetrievalService.retrieve()`.

2. **Test on larger corpus** — The 38-chunk fixture set is too small for BM25 to show its value. Test on the full knowledge base (the user's actual documents).

3. **Consider hybrid-specific chunk matching** — The eval could be updated to match at `doc_id` level for hybrid comparison, since hybrid may surface different (but equally valid) chunks from the same document.

4. **Tune BM25 parameters** — Try different `bm25_top_k` values or BM25 scoring variants (e.g., BM25L, BM25+) that handle short documents better.

**Recommendation:** Fix the RRF intra-document reordering issue first (item 1), then re-run the comparison. If recall improves, proceed to cross-encoder reranker. If not, the hybrid retrieval architecture needs deeper analysis before adding more complexity.
