# MindDock Evaluation Report

- Dataset: `eval\benchmark\pdf_benchmark.jsonl`
- Generated at: `2026-04-18T11:20:14+00:00`
- Dataset size: **20**
- Task counts: chat=2, compare=4, search=14

## Retrieval Metrics

| Metric | Value |
| --- | ---: |
| hit@1 | 50.00% |
| hit@3 | 55.00% |
| hit@5 | 65.00% |

## Citation Consistency

| Metric | Value |
| --- | ---: |
| Overall consistency rate | 65.00% |
| Structure consistency rate | 100.00% |
| Expected-source consistency rate | 56.25% |
| Expected-source case count | 16 |

## Latency Summary

| Scope | Avg (ms) | P50 (ms) | P95 (ms) | Max (ms) | Samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| overall | 1137.35 | 23.66 | 8115.76 | 13253.46 | 20 |
| chat | 10549.40 | 10549.40 | 12983.05 | 13253.46 | 2 |
| compare | 297.69 | 362.67 | 435.47 | 446.20 | 4 |
| search | 32.68 | 21.73 | 85.44 | 176.28 | 14 |

## Failed Cases

- `search_agentic_rag_taxonomy` (search): retrieval_miss@5
- `search_pkm_methods` (search): retrieval_miss@5
- `search_acl_context` (search): retrieval_miss@5, citation_expected_source_miss
- `search_naacl_experiments` (search): retrieval_miss@5, citation_expected_source_miss
- `search_arxiv2309` (search): retrieval_miss@5, citation_expected_source_miss
- `compare_agentic_rag_vs_milvus` (compare): retrieval_miss@5, citation_expected_source_miss
- `compare_pkm_vs_vector` (compare): citation_expected_source_miss
- `compare_lost_vs_rag` (compare): citation_expected_source_miss
- `compare_architecture_md` (compare): citation_expected_source_miss
- `meta_general_abstract` (search): retrieval_miss@5

## Case Details

| Case | Task | hit@1 | hit@3 | hit@5 | Citation | Latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `search_agentic_rag_taxonomy` | search | N | N | N | Y | 176.28 |
| `search_lost_middle_context` | search | N | N | Y | Y | 23.32 |
| `search_milvus_features` | search | Y | Y | Y | Y | 32.28 |
| `search_pkm_methods` | search | N | N | N | Y | 36.52 |
| `search_vector_compare` | search | Y | Y | Y | Y | 22.43 |
| `search_acl_context` | search | N | N | N | N | 24.14 |
| `search_naacl_experiments` | search | N | N | N | N | 21.02 |
| `search_arxiv2309` | search | N | N | N | N | 23.99 |
| `chat_agentic_rag` | chat | Y | Y | Y | Y | 13253.46 |
| `chat_lost_middle` | chat | Y | Y | Y | Y | 7845.35 |
| `meta_abstract_general` | search | Y | Y | Y | Y | 14.21 |
| `meta_author_general` | search | Y | Y | Y | Y | 14.74 |
| `meta_references_general` | search | Y | Y | Y | Y | 15.55 |
| `compare_agentic_rag_vs_milvus` | compare | N | N | N | N | 19.20 |
| `compare_pkm_vs_vector` | compare | Y | Y | Y | N | 350.64 |
| `compare_lost_vs_rag` | compare | Y | Y | Y | N | 374.70 |
| `search_ai_agent_kb` | search | N | N | Y | Y | 17.49 |
| `compare_architecture_md` | compare | N | Y | Y | N | 446.20 |
| `meta_general_abstract` | search | N | N | N | Y | 17.48 |
| `search_crad_english` | search | Y | Y | Y | Y | 18.07 |