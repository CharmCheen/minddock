# MindDock Evaluation Report

- Dataset: `eval\benchmark\sample_eval_set.jsonl`
- Generated at: `2026-04-18T11:16:58+00:00`
- Dataset size: **13**
- Task counts: chat=4, compare=3, search=6

## Retrieval Metrics

| Metric | Value |
| --- | ---: |
| hit@1 | 46.15% |
| hit@3 | 46.15% |
| hit@5 | 46.15% |

## Citation Consistency

| Metric | Value |
| --- | ---: |
| Overall consistency rate | 69.23% |
| Structure consistency rate | 100.00% |
| Expected-source consistency rate | 50.00% |
| Expected-source case count | 8 |

## Latency Summary

| Scope | Avg (ms) | P50 (ms) | P95 (ms) | Max (ms) | Samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| overall | 1282.58 | 332.20 | 4496.69 | 4952.51 | 13 |
| chat | 3858.48 | 3923.84 | 4838.56 | 4952.51 | 4 |
| compare | 348.48 | 343.99 | 366.73 | 369.26 | 3 |
| search | 32.37 | 15.50 | 91.88 | 116.87 | 6 |

## Failed Cases

- `search_retrieval_flow` (search): retrieval_miss@5
- `search_source_lifecycle` (search): retrieval_miss@5
- `chat_architecture_flow` (chat): retrieval_miss@5, citation_expected_source_miss
- `chat_insufficient_token_rotation` (chat): retrieval_miss@5
- `compare_architecture_vs_rag` (compare): retrieval_miss@5, citation_expected_source_miss
- `compare_example_vs_api` (compare): retrieval_miss@5, citation_expected_source_miss
- `compare_storage_approaches` (compare): retrieval_miss@5, citation_expected_source_miss

## Case Details

| Case | Task | hit@1 | hit@3 | hit@5 | Citation | Latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `search_storage_chroma` | search | Y | Y | Y | Y | 116.87 |
| `search_extension_points` | search | Y | Y | Y | Y | 15.05 |
| `search_retrieval_flow` | search | N | N | N | Y | 15.00 |
| `search_ingest_endpoint` | search | Y | Y | Y | Y | 16.91 |
| `search_source_lifecycle` | search | N | N | N | Y | 15.94 |
| `search_example_citations` | search | Y | Y | Y | Y | 14.42 |
| `chat_citation_fields` | chat | Y | Y | Y | Y | 4192.81 |
| `chat_architecture_flow` | chat | N | N | N | N | 3654.86 |
| `chat_supported_filters` | chat | Y | Y | Y | Y | 4952.51 |
| `chat_insufficient_token_rotation` | chat | N | N | N | Y | 2633.75 |
| `compare_architecture_vs_rag` | compare | N | N | N | N | 332.20 |
| `compare_example_vs_api` | compare | N | N | N | N | 369.26 |
| `compare_storage_approaches` | compare | N | N | N | N | 343.99 |