# P1 Hybrid Full KB Validation Result

## 1. Branch and Commit

- Branch: `mac-p1-hybrid-full-kb-validation` (from `mac-p1-hybrid-rrf-diagnostics`)
- Base commit: `3444e2c Stabilize hybrid RRF same-document ranking`
- Date: 2026-05-29

## 2. Validation Scope

**Partial validation only.** The golden eval set (`eval/benchmark/golden_eval_set.jsonl`) was designed for the 5-fixture-file knowledge base. A true full-KB validation requires a new eval dataset covering the user's actual 39-file knowledge base (26 PDFs, 2 MP4, 3 JPG, 6 MD, 1 MP3).

What was validated:
- 8 search cases against the fixture-only Chroma (38 chunks, 5 docs)
- Same-doc RRF fix confirmed: hybrid matches dense (no regression)
- Hybrid does NOT improve recall on this fixture set

What was NOT validated:
- Full 39-file KB (ingest stuck on media files; PDF processing slow)
- Chat/compare tasks (require LLM API key not available in this environment)
- Larger eval dataset covering actual KB content

## 3. KB and Dataset Used

| Item | Value |
| --- | --- |
| KB source | `data/eval_fixtures_kb/` (5 markdown files) |
| Chroma dir | `data/chroma/` |
| Chunk count | 38 |
| Document count | 5 |
| Eval dataset | `eval/benchmark/golden_eval_set.jsonl` |
| Eval cases | 19 total (8 search, 8 chat, 3 compare) |
| Cases run | 8 search (chat/compare require LLM) |

**Full KB status**: Attempted ingest of 32 text files (26 PDFs + 6 MD). Process stuck on large PDFs after processing 11 documents (1183 chunks). The 5 fixture files were not yet reached when the process was stopped. A separate full-KB eval dataset does not exist.

## 4. Commands Run

```bash
# Fixture-only comparison (search tasks)
python scripts/evaluate_rag.py --dataset eval/benchmark/golden_eval_set.jsonl \
    --output-dir data/eval --retrieval-mode compare
```

Filtered to `task_types=('search',)` programmatically due to missing LLM API key for chat/compare tasks.

## 5. Dense Metrics (search, 8 cases)

| Metric | Value |
| --- | ---: |
| hit@1 | 25.00% |
| hit@3 | 50.00% |
| hit@5 | 50.00% |
| Citation overall consistency | 100.00% |
| Citation source accuracy | 100.00% |
| IE accuracy | 100.00% |
| Avg latency | 286.25ms |

## 6. Hybrid Metrics (search, 8 cases)

| Metric | Value |
| --- | ---: |
| hit@1 | 25.00% |
| hit@3 | 50.00% |
| hit@5 | 50.00% |
| Citation overall consistency | 100.00% |
| Citation source accuracy | 100.00% |
| IE accuracy | 100.00% |
| Avg latency | 281.47ms |

## 7. Metric Delta

| Metric | Dense | Hybrid | Delta |
| --- | ---: | ---: | ---: |
| hit@1 | 25.00% | 25.00% | 0.00% |
| hit@3 | 50.00% | 50.00% | 0.00% |
| hit@5 | 50.00% | 50.00% | 0.00% |
| Citation overall | 100.00% | 100.00% | 0.00% |
| IE accuracy | 100.00% | 100.00% | 0.00% |
| Avg latency | 286.25ms | 281.47ms | -4.78ms |

## 8. Per-Case Changes

| Case | Dense hit@1/3/5 | Hybrid hit@1/3/5 | Status |
| --- | --- | --- | --- |
| search_storage_chroma | N/Y/Y | N/Y/Y | same |
| search_extension_points | N/N/N | N/N/N | same |
| search_retrieval_flow | Y/Y/Y | Y/Y/Y | same (was N/Y/Y before RRF fix) |
| search_ingest_endpoint | N/N/N | N/N/N | same |
| search_source_lifecycle | N/N/N | N/N/N | same |
| search_example_citations | N/N/N | N/N/N | same |
| search_hybrid_retrieval | Y/Y/Y | Y/Y/Y | same |
| search_metadata_filters | N/Y/Y | N/Y/Y | same |

- **Hybrid improved**: 0 cases
- **Hybrid degraded**: 0 cases (was 2 before RRF fix)
- **Same**: 8 cases
- **Dense miss, hybrid hit**: 0 cases
- **Hybrid miss, dense hit**: 0 cases

## 9. Remaining Risks

1. **No positive hybrid signal**: On this 38-chunk fixture set, BM25 adds no retrieval value. This is expected — BM25's strength is in larger, more diverse corpora where lexical matching surfaces documents that dense embeddings miss.

2. **Full KB not validated**: The 39-file KB (26 PDFs + media) was not fully ingested. PDF processing is slow and the process timed out. A true full-KB validation needs:
   - A completed ingest of all documents
   - A new eval dataset with queries/expected docs covering the actual KB content
   - Sufficient time for PDF parsing and embedding

3. **Chat/compare not tested**: These tasks require an LLM API key. The full pipeline (retrieval → generation → citation) may behave differently with hybrid retrieval.

4. **Fixture set is too small for BM25**: 38 chunks / 5 docs doesn't exercise BM25's value. BM25 excels at:
   - Large corpora (hundreds/thousands of docs)
   - Exact term matching (technical terms, acronyms, proper nouns)
   - Cross-lingual retrieval (Chinese/English mixed content)

5. **Chunk-level eval strictness**: The eval checks `expected_chunk_ids` (exact chunk match). Even when hybrid finds the right document, it may return a different chunk, causing false negatives.

## 10. Can We Proceed To Cross-Encoder Reranker?

**No. Insufficient evidence.**

The golden eval set is designed for the 5-fixture-file KB. On this set, hybrid retrieval shows:
- No recall improvement over dense
- No recall degradation (after RRF same-doc fix)
- Slight latency improvement (-4.78ms)

This is **not sufficient evidence** to justify adding a cross-encoder reranker. The reasons:

1. **No positive hybrid signal**: Hybrid doesn't improve recall, so there's no retrieval foundation for a reranker to optimize over.

2. **Full KB not tested**: BM25's value emerges with larger, more diverse corpora. The 38-chunk fixture set is too small.

3. **No larger eval dataset**: A new eval dataset covering the actual 39-file KB is needed before any retrieval strategy decision.

**Recommended next steps**:
1. Complete full KB ingest (requires patience for PDF processing)
2. Create a new eval dataset with queries/expected docs covering the actual KB content
3. Run dense vs hybrid comparison on the full KB eval dataset
4. If hybrid shows recall improvement on the full KB, then proceed to cross-encoder reranker
5. If hybrid still doesn't improve, consider whether the embedding model or chunking strategy needs improvement before adding more retrieval layers
