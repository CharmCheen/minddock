# MindDock Evaluation Report

- Dataset: `eval\benchmark\sample_eval_set.jsonl`
- Generated at: `2026-04-07T12:40:03+00:00`
- Dataset size: **10**
- Task counts: chat=4, compare=2, search=4

## Retrieval Metrics

| Metric | Value |
| --- | ---: |
| hit@1 | 50.00% |
| hit@3 | 60.00% |
| hit@5 | 60.00% |

## Citation Consistency

| Metric | Value |
| --- | ---: |
| Overall consistency rate | 70.00% |
| Structure consistency rate | 100.00% |
| Expected-source consistency rate | 57.14% |
| Expected-source case count | 7 |

## Latency Summary

| Scope | Avg (ms) | P50 (ms) | P95 (ms) | Max (ms) | Samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| overall | 2372.82 | 188.19 | 7919.83 | 10477.76 | 10 |
| chat | 5764.50 | 4611.22 | 9625.12 | 10477.76 | 4 |
| compare | 188.19 | 188.19 | 190.03 | 190.24 | 2 |
| search | 73.46 | 45.58 | 142.92 | 160.08 | 4 |

## Failed Cases

- `search_retrieval_flow` (search): retrieval_miss@5
- `chat_architecture_flow` (chat): retrieval_miss@5, citation_expected_source_miss
- `chat_insufficient_token_rotation` (chat): retrieval_miss@5
- `compare_architecture_vs_rag` (compare): retrieval_miss@5, citation_expected_source_miss
- `compare_example_vs_api` (compare): citation_expected_source_miss

## Case Details

| Case | Task | hit@1 | hit@3 | hit@5 | Citation | Latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `search_storage_chroma` | search | Y | Y | Y | Y | 160.08 |
| `search_extension_points` | search | Y | Y | Y | Y | 45.50 |
| `search_retrieval_flow` | search | N | N | N | Y | 45.66 |
| `chat_citation_fields` | chat | Y | Y | Y | Y | 3357.82 |
| `chat_architecture_flow` | chat | N | N | N | N | 10477.76 |
| `chat_supported_filters` | chat | Y | Y | Y | Y | 4428.95 |
| `chat_insufficient_token_rotation` | chat | N | N | N | Y | 4793.48 |
| `compare_architecture_vs_rag` | compare | N | N | N | N | 190.24 |
| `compare_example_vs_api` | compare | N | Y | Y | N | 186.13 |
| `search_ingest_endpoint` | search | Y | Y | Y | Y | 42.60 |