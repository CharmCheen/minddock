# Service Model

## Purpose

This document describes the formal application-layer result objects introduced in stage 8.

The source layer and retrieval layer were already formalized earlier. This layer keeps the use-case/service contracts explicit, and the newer application/orchestrator layer now composes these service results for frontend-facing consumers.

## Layer Boundary

Current intended flow:

```text
request schema
  -> application facade / orchestrator
  -> service
  -> service result
  -> presenter
  -> response schema
```

Supporting workflow flow:

```text
service
  -> workflow
  -> workflow preparation result
  -> service result
```

## Core Service Result Objects

### `UseCaseMetadata`

Shared metadata container for service outputs.

Current fields:

- `retrieved_count`
- `mode`
- `output_format`
- `partial_failure`
- `insufficient_evidence`
- `empty_result`
- `warnings`
- `issues`
- `timing`
- `runtime_mode`
- `provider_mode`
- `filter_applied`
- `source_stats`
- `retrieval_stats`
- `debug_notes`

This is intentionally small. It provides a common place for additive metadata without forcing a large envelope into every layer.

### Retrieval pipeline reflection

The unified retrieval pipeline (CHAT/SUMMARIZE) now carries a small reflection record in its final state:

- `quality_ok` — whether the retrieved evidence passed the rule-based quality gate
- `quality_reasons` — list of human-readable failure reasons (e.g. "No hits retrieved", "Insufficient diversity for summarize")
- `low_confidence` — set when all retrieval distances are weak (`>= 1.5`)
- `reflection` — includes `attempt` count and `reasons` for observability
- `retry_count` / `max_retries` — bounded retry bookkeeping (currently `max_retries = 1`)
- `original_query` / `expanded_query` — preserved when a retry expansion was applied

These fields are additive and do not break existing service result contracts.

### `SearchServiceResult`

Wraps:

- `SearchResult`
- `UseCaseMetadata`

Purpose:

- keep search as a formal use-case result
- allow presenter and non-HTTP consumers to read both search hits and use-case metadata

### `ChatServiceResult`

Fields:

- `answer`
- `citations`
- `metadata`
- `context`

Purpose:

- represent both grounded success and insufficient-evidence outcomes
- preserve traceable citations without returning dict-heavy payloads from the service

### `SummarizeServiceResult`

Fields:

- `summary`
- `citations`
- `metadata`
- `structured_output`
- `context`

Purpose:

- unify basic summarize, map-reduce summarize, and Mermaid structured output

### `CompareServiceResult`

Fields:

- `compare_result`
- `citations`
- `metadata`
- `context`

Purpose:

- represent grounded multi-document compare outcomes
- preserve `common_points`, `differences`, and `conflicts` with paired evidence
- keep the compare use-case composable for both direct `/compare` routes and unified execution

### `IntentClassificationResult`

Fields:

- `task_type` — inferred `TaskType` (`CHAT`, `SUMMARIZE`, or `COMPARE`)
- `confidence` — match confidence (`0.9` strong, `0.65` weak, `0.5` fallback)
- `reason` — human-readable classification reason
- `matched_keyword` — the keyword that triggered the match, or `None`
- `user_override` — `True` when the user explicitly provided a `task_type`

Purpose:

- lightweight, deterministic intent classification without LLM inference
- used by `FrontendFacade.execute_run()` to resolve `task_type` when the frontend omits it (auto mode)
- keyword lists cover both Chinese and English compare/summarize terms
- preserves explicit user choice via `user_override=True`

### `IngestServiceResult`

Wraps:

- `IngestBatchResult`
- `UseCaseMetadata`

Purpose:

- express partial-failure semantics at the service layer
- keep ingest reusable outside HTTP routes

### `CatalogServiceResult`

Fields:

- `entries`
- `metadata`

Purpose:

- list currently indexed sources without exposing raw vector-store rows

### `SourceDetailServiceResult`

Fields:

- `found`
- `detail`
- `metadata`

Purpose:

- return stable source-detail lookups by `doc_id` or exact `source`

### `DeleteSourceServiceResult`

Fields:

- `result`
- `metadata`

Purpose:

- express source deletion as a normal lifecycle result instead of an exception path

### `ReingestSourceServiceResult`

Fields:

- `found`
- `source_result`
- `metadata`

Purpose:

- re-run one source through the existing ingest path
- preserve partial-failure and warning semantics for lifecycle management

## Workflow Result Objects

### `RetrievalPreparationResult`

Fields:

- `hits`
- `grounded_hits`
- `context`
- `citations`
- `grouped_hits`

This is the prepared workflow output consumed by summarize-oriented orchestration.

### `DocumentEvidenceGroup`

Fields:

- `doc_id`
- `hits`
- `citation`
- `context`

This replaces older grouped evidence dicts.

## Responsibility Split

### Service layer

Owns:

- use-case orchestration
- success/empty/insufficient-evidence semantics
- service-level metadata
- composition of retrieval/source domain objects into reusable application results

### Workflow layer

Owns:

- graph state progression
- retrieval preparation
- grouped evidence organization

### Presenter layer

Owns:

- mapping service results to response schemas only

## Compatibility Notes

This stage is intentionally non-breaking:

- routes still expose the same endpoint paths
- response payloads remain JSON-compatible
- some service results still provide lightweight `to_api_dict()` compatibility helpers for internal utilities and gradual migration

## Internal Consumers

Current preferred internal consumers:

- `app/demo.py`
- `app/eval/rag_eval.py`
- `scripts/evaluate_rag.py`
- source catalog/lifecycle commands in `app/demo.py`

Preferred rule:

- internal tools consume service results directly
- HTTP adapters consume presenter/response schemas

The remaining `to_api_dict()` helpers are transitional compatibility aids for lightweight internal tooling and tests. They are not the preferred main path for new consumers.

## Future Extension Points

Good future additions, if needed:

- structured `warnings` objects instead of plain strings
- timing/debug metadata in `UseCaseMetadata`
- non-HTTP adapters that consume service results directly for CLI or desktop workflows

## Relationship To The Application Layer

Current architectural rule:

- services remain the main use-case implementation units
- orchestrators/facades sit above them and should be preferred by future frontend callers
- presenters should not bypass service results to understand low-level retrieval/source internals

This keeps the service model reusable while still allowing a higher-level entrypoint for UI integration.
