# MindDock Evaluation Report

- Dataset: `eval\benchmark\pdf_benchmark.jsonl`
- Generated at: `2026-04-18T16:05:21+00:00`
- Dataset size: **20**
- Task counts: chat=2, compare=4, search=14

## Retrieval Metrics

| Metric | Value |
| --- | ---: |
| hit@1 | 75.00% |
| hit@3 | 85.00% |
| hit@5 | 95.00% |

## Citation Consistency

| Metric | Value |
| --- | ---: |
| Overall consistency rate | 85.00% |
| Structure consistency rate | 100.00% |
| Expected-source consistency rate | 81.25% |
| Expected-source case count | 16 |

## Latency Summary

| Scope | Avg (ms) | P50 (ms) | P95 (ms) | Max (ms) | Samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| overall | 915.41 | 20.30 | 7028.00 | 9402.61 | 20 |
| chat | 8152.82 | 8152.82 | 9277.63 | 9402.61 | 2 |
| compare | 397.29 | 396.88 | 417.44 | 418.10 | 4 |
| search | 29.54 | 18.39 | 73.46 | 167.96 | 14 |

## Failed Cases

- `compare_pkm_vs_vector` (compare): citation_expected_source_miss
- `compare_lost_vs_rag` (compare): citation_expected_source_miss
- `compare_architecture_md` (compare): retrieval_miss@5, citation_expected_source_miss

## Case Details

| Case | Task | hit@1 | hit@3 | hit@5 | Citation | Latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `search_agentic_rag_taxonomy` | search | Y | Y | Y | Y | 167.96 |
| `search_lost_middle_context` | search | N | N | Y | Y | 18.11 |
| `search_milvus_features` | search | Y | Y | Y | Y | 22.57 |
| `search_pkm_methods` | search | Y | Y | Y | Y | 21.83 |
| `search_vector_compare` | search | Y | Y | Y | Y | 18.11 |
| `search_acl_context` | search | Y | Y | Y | Y | 17.60 |
| `search_naacl_experiments` | search | Y | Y | Y | Y | 21.35 |
| `search_arxiv2309` | search | Y | Y | Y | Y | 18.03 |
| `chat_agentic_rag` | chat | Y | Y | Y | Y | 9402.61 |
| `chat_lost_middle` | chat | Y | Y | Y | Y | 6903.02 |
| `meta_abstract_general` | search | Y | Y | Y | Y | 19.00 |
| `meta_author_general` | search | Y | Y | Y | Y | 18.09 |
| `meta_references_general` | search | Y | Y | Y | Y | 19.25 |
| `compare_agentic_rag_vs_milvus` | compare | Y | Y | Y | Y | 418.10 |
| `compare_pkm_vs_vector` | compare | Y | Y | Y | N | 377.31 |
| `compare_lost_vs_rag` | compare | N | Y | Y | N | 413.73 |
| `search_ai_agent_kb` | search | N | N | Y | Y | 18.68 |
| `compare_architecture_md` | compare | N | N | N | N | 380.03 |
| `meta_general_abstract` | search | N | Y | Y | Y | 15.36 |
| `search_crad_english` | search | Y | Y | Y | Y | 17.55 |