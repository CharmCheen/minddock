# P1 Hybrid RRF Diagnostics

## 1. Branch and Commit

- Branch: `mac-p1-hybrid-rrf-diagnostics` (from `mac-p1-hybrid-retrieval`)
- Base commit: `6d30625 Enable evaluable hybrid retrieval baseline`
- Date: 2026-05-29

## 2. Problem Recap

P1 initial comparison showed hybrid retrieval regressing recall vs dense:
- hit@1: 25% → 12.5% (dense → hybrid)
- hit@3: 50% → 37.5%
- hit@5: 50% → 50% (unchanged)

Two cases degraded: `search_storage_chroma` (lost hit@3) and `search_retrieval_flow` (lost hit@1).

Hypothesis: RRF fusion reorders chunks within the same document when BM25 promotes a different chunk from the same doc, and the eval expects specific `chunk_id` matches.

## 3. Dense vs BM25 vs Hybrid Per-Case Findings

### search_retrieval_flow (CHANGED: lost hit@1)
| Rank | Dense | BM25 | Hybrid |
| ---: | --- | --- | --- |
| 1 | rag_pipeline.md:3 **(expected)** | rag_pipeline.md:2 | rag_pipeline.md:2 |
| 2 | example.md:0 | architecture.md:3 | example.md:0 |
| 3 | example.md:1 | example.md:0 | rag_pipeline.md:3 **(expected)** |

**Diagnosis**: Same-doc reordered. `rag_pipeline.md:2` appears in both dense (rank 4) and BM25 (rank 1), getting RRF dual-list boost above `rag_pipeline.md:3` (dense rank 1 only). Expected chunk demoted from rank 1 to rank 3.

### search_storage_chroma (CHANGED: lost hit@3)
| Rank | Dense | BM25 | Hybrid |
| ---: | --- | --- | --- |
| 1 | example.md:1 | example.md:1 | example.md:1 |
| 2 | example.md:0 **(expected chunk)** | README.md:10 | README.md:10 |
| 3 | README.md:10 | architecture.md:3 | rag_pipeline.md:3 |
| 4 | README.md:0 | rag_pipeline.md:6 | example.md:0 **(expected chunk)** |

**Diagnosis**: `README.md:10` gets BM25 boost (appears in both dense rank 3 and BM25 rank 2), promoting it above `example.md:0` (dense rank 2 only). Expected chunk demoted from rank 2 to rank 4.

### search_ingest_endpoint (UNCHANGED: both miss)
Expected doc present in dense but expected chunk missing. Hybrid also has expected doc present but chunk missing. Same-doc reordering in both modes.

### search_source_lifecycle (UNCHANGED: both miss)
Dense has expected doc at rank 1 (api_usage.md:5) but expected chunk is api_usage.md:4. Hybrid also has api_usage.md at rank 1. Same-doc chunk mismatch in both modes.

### search_example_citations (UNCHANGED: both miss)
Expected chunk is example.md:1, but neither dense nor hybrid returns it in top 5. Dense returns example.md:0 and example.md:2; hybrid reorders these. The expected chunk is simply not retrieved.

### Other cases (UNCHANGED)
- `search_extension_points`: Both miss (expected doc not in top-5)
- `search_hybrid_retrieval`: Both hit (expected chunk at rank 1 in both)
- `search_metadata_filters`: Both hit@3 (expected chunk at rank 2 in both)

## 4. Root Cause

**Confirmed**: RRF dual-list boost causes same-document chunk reordering.

Mechanism:
1. BM25 ranks chunks by lexical term overlap, often preferring different chunks from the same document than dense
2. When a chunk appears in both dense and BM25 results, RRF adds both scores: `1/(k+dense_rank) + 1/(k+bm25_rank)`
3. A chunk at dense rank 4 + BM25 rank 1 gets score `1/64 + 1/61 = 0.032`
4. A chunk at dense rank 1 only gets score `1/61 = 0.016`
5. The BM25-boosted chunk outranks the dense-preferred chunk

This is problematic when the evaluation expects specific `chunk_id` matches (not just `doc_id`).

**Secondary factor**: Small fixture set (38 chunks, 5 docs). BM25 IDF signal is weak; many terms appear across most documents, so BM25 returns noisy results.

## 5. Fix Applied

**Same-doc dense-rank preservation**: After RRF fusion, group results by `doc_id` and sort within each group by dense rank (ascending). This preserves the within-document ordering from dense retrieval while keeping the cross-document RRF ranking.

Change in `app/rag/hybrid_retrieval.py` — `HybridRetrievalService.retrieve()`:
- Before: RRF fused list used directly as result order
- After: Candidates grouped by `doc_id`, each group sorted by `dense_rank`, then flattened

This is a minimal change that:
- Prevents BM25 from reordering chunks within the same document
- Preserves cross-document RRF ranking (documents still ordered by RRF score)
- Does not affect citation metadata
- Does not hardcode any fixture-specific logic

## 6. Tests Run

```
tests/unit/test_evaluation_fixtures.py        — 11 passed
tests/unit/test_evaluation.py                 — 18 passed
tests/unit/test_rag_eval.py                   — 1 passed
tests/unit/test_hybrid_retrieval.py           — 6 passed
tests/unit/test_hybrid_retrieval_edges.py     — 7 passed
tests/unit/test_hybrid_retrieval_debug.py     — 5 passed
tests/unit/test_rrf_fusion.py                 — 8 passed
tests/unit/test_evaluation_hybrid.py          — 6 passed
────────────────────────────────────────────
Total: 68 passed, 0 failed
```

New tests added:
- `test_rrf_same_doc_chunk_reordering_demonstrated` — Demonstrates the RRF dual-list boost mechanism
- `test_hybrid_retrieve_same_doc_dense_order_preserved` — Verifies the fix preserves dense ordering within same doc
- `test_rrf_fuse_*` — 8 RRF fusion behavior tests

## 7. Metrics Before vs After

### Before fix (P1 initial)
| Metric | Dense | Hybrid | Delta |
| --- | ---: | ---: | ---: |
| hit@1 | 25.00% | 12.50% | -12.50% |
| hit@3 | 50.00% | 37.50% | -12.50% |
| hit@5 | 50.00% | 50.00% | 0.00% |
| Citation | 100% | 100% | 0% |
| Latency | 315ms | 302ms | -13ms |

### After fix (same-doc preservation)
| Metric | Dense | Hybrid | Delta |
| --- | ---: | ---: | ---: |
| hit@1 | 25.00% | 25.00% | 0.00% |
| hit@3 | 50.00% | 50.00% | 0.00% |
| hit@5 | 50.00% | 50.00% | 0.00% |
| Citation | 100% | 100% | 0% |
| Latency | 340ms | 315ms | -25ms |

The fix eliminates the recall regression. Hybrid now matches dense exactly.

## 8. Remaining Risks

1. **No recall improvement**: Hybrid matches dense but doesn't improve it. BM25 doesn't surface new relevant documents on this 38-chunk fixture set. On a larger, more diverse corpus, BM25 may help.

2. **Same-doc fix is conservative**: The fix preserves dense ordering within documents, which means BM25's contribution is limited to cross-document ranking. If BM25 correctly identifies a better chunk from the same document, that signal is now lost.

3. **Fixture set too small**: 38 chunks / 5 docs is not representative. BM25's value is in surfacing lexically relevant documents that dense embeddings miss — this requires a larger corpus with more topic diversity.

4. **Chunk-level eval strictness**: The eval checks `expected_chunk_ids` (exact chunk match). For cases like `search_ingest_endpoint`, the expected doc is found but the expected chunk isn't in top-5. This is a retrieval quality issue, not a fusion issue.

5. **Chat/compare not tested**: Full pipeline (retrieval → generation → citation) may behave differently. Requires LLM access.

## 9. Can We Proceed To Cross-Encoder Reranker?

**No, not yet.** The reasons:

1. **Hybrid doesn't improve recall**: On this fixture set, hybrid matches dense but doesn't beat it. A cross-encoder reranker would be optimizing over a retrieval result that isn't better than the baseline.

2. **Fixture set too small**: The 38-chunk corpus doesn't exercise BM25's strength (surfacing lexically relevant docs from a large corpus). We need to test on the full knowledge base first.

3. **Several dense-only failures remain**: 4 out of 8 search cases fail even with dense retrieval (`search_extension_points`, `search_ingest_endpoint`, `search_source_lifecycle`, `search_example_citations`). These need investigation before adding more retrieval layers.

**Recommended next steps before cross-encoder**:
1. Test on the full knowledge base (user's actual documents, not just fixtures)
2. Investigate the 4 persistent dense failures — are they query-fixture mismatches or genuine retrieval quality issues?
3. Consider whether the chunk-level eval is too strict for hybrid comparison (doc-level matching may be more appropriate)
4. If hybrid shows recall improvement on the full corpus, then proceed to cross-encoder reranker
