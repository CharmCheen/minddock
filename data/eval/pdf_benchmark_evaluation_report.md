# MindDock Evaluation Report

- Dataset: `eval\benchmark\pdf_benchmark.jsonl`
- Generated at: `2026-04-19T03:25:18+00:00`
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
| Overall consistency rate | 90.00% |
| Structure consistency rate | 100.00% |
| Expected-source consistency rate | 87.50% |
| Expected-source case count | 16 |

## Latency Summary

| Scope | Avg (ms) | P50 (ms) | P95 (ms) | Max (ms) | Samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| overall | 1078.03 | 20.73 | 9473.22 | 9891.65 | 20 |
| chat | 9671.42 | 9671.42 | 9869.63 | 9891.65 | 2 |
| compare | 458.14 | 449.71 | 503.97 | 512.85 | 4 |
| search | 27.51 | 18.76 | 64.21 | 139.97 | 14 |

## Failed Cases

- `compare_lost_vs_rag` (compare): citation_expected_source_miss
- `compare_architecture_md` (compare): retrieval_miss@5, citation_expected_source_miss

## Case Details

| Case | Task | hit@1 | hit@3 | hit@5 | Citation | Latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `search_agentic_rag_taxonomy` | search | Y | Y | Y | Y | 139.97 |
| `search_lost_middle_context` | search | N | N | Y | Y | 18.39 |
| `search_milvus_features` | search | Y | Y | Y | Y | 16.77 |
| `search_pkm_methods` | search | Y | Y | Y | Y | 17.78 |
| `search_vector_compare` | search | Y | Y | Y | Y | 17.35 |
| `search_acl_context` | search | Y | Y | Y | Y | 19.13 |
| `search_naacl_experiments` | search | Y | Y | Y | Y | 23.41 |
| `search_arxiv2309` | search | Y | Y | Y | Y | 17.54 |
| `chat_agentic_rag` | chat | Y | Y | Y | Y | 9891.65 |
| `chat_lost_middle` | chat | Y | Y | Y | Y | 9451.20 |
| `meta_abstract_general` | search | Y | Y | Y | Y | 15.80 |
| `meta_author_general` | search | Y | Y | Y | Y | 22.45 |
| `meta_references_general` | search | Y | Y | Y | Y | 19.64 |
| `compare_agentic_rag_vs_milvus` | compare | Y | Y | Y | Y | 512.85 |
| `compare_pkm_vs_vector` | compare | Y | Y | Y | Y | 453.65 |
| `compare_lost_vs_rag` | compare | N | Y | Y | N | 445.78 |
| `search_ai_agent_kb` | search | N | N | Y | Y | 21.81 |
| `compare_architecture_md` | compare | N | N | N | N | 420.30 |
| `meta_general_abstract` | search | N | Y | Y | Y | 15.63 |
| `search_crad_english` | search | Y | Y | Y | Y | 19.44 |