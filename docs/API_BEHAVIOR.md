# API Behavior

## Shared Principles

The API is designed around five principles:

1. validation errors should have a shared JSON shape
2. service failures should include a request identifier
3. lack of evidence is a normal grounded outcome, not an exception
4. search/chat/summarize should share one retrieval/filter model
5. internal model formalization should not casually break external API compatibility
6. route handlers should stay thin and delegate serialization to explicit response models

## Endpoints

### `POST /ingest`

Request:

- `rebuild: bool = false`
- `urls: list[str] = []`

Behavior:

- ingests local knowledge-base files every time
- additionally ingests any URLs supplied in `urls`
- supports partial success
- internally uses `IngestBatchResult`
- route layer serializes through `IngestResponse.from_result()`

Response:

- `documents`
- `chunks`
- `ingested_sources`
- `failed_sources`
- `partial_failure`

### `POST /search`

Request:

- `query`
- `top_k`
- `filters`

Behavior:

- internally returns `SearchResult`
- route layer serializes through `SearchResponse.from_result()`

### `GET /sources`

Query:

- optional `source_type`

Behavior:

- lists indexed sources aggregated from stored chunk metadata
- route layer serializes through `SourceCatalogResponse.from_result()`

### `GET /sources/{doc_id}` and `GET /sources/by-source`

Behavior:

- resolve indexed source detail by `doc_id` or exact `source`
- return `found=false` when the target cannot be resolved
- accept optional `include_admin_metadata=true` for a controlled admin/debug block

### `GET /sources/{doc_id}/chunks` and `GET /sources/by-source/chunks`

Query:

- `limit`
- `offset`
- `include_admin_metadata`

Behavior:

- resolve one source by `doc_id` or exact `source`
- return source summary plus paginated chunk previews
- `limit` and `offset` are validated at the route boundary
- return `found=false` when the target cannot be resolved
- keep preview text truncated and readable instead of returning a raw chunk dump

### `DELETE /sources/{doc_id}` and `DELETE /sources/by-source`

Behavior:

- delete one indexed source by `doc_id` or exact `source`
- return a structured deletion result rather than treating “not found” as an exception

### `POST /sources/{doc_id}/reingest` and `POST /sources/by-source/reingest`

Behavior:

- reingest one source by `doc_id` or exact `source`
- file sources rebuild from the current knowledge-base path
- URL sources refetch from the stored/resolved URL
- `source`-based reingest can still run even if the source was deleted from the current catalog

### `POST /chat`

Request:

- `query`
- `top_k`
- `filters`

Behavior:

- uses the same `RetrievedChunk` / `RetrievalFilters` flow as `/search`
- no-evidence remains a normal grounded response
- route layer serializes through `ChatResponse.from_result()`

### `POST /summarize`

Request:

- `query` or `topic`
- `top_k`
- `filters`
- `mode`
- `output_format`

Behavior:

- uses the same retrieval/filter model as `/search` and `/chat`
- no-evidence remains a normal grounded response
- route layer serializes through `SummarizeResponse.from_result()`

### `POST /compare`

Request:

- `question`
- `top_k`
- `filters`

Behavior:

- performs grounded multi-document comparison over retrieved evidence groups
- requires at least 2 distinct document groups to produce a meaningful comparison
- returns `insufficient_evidence` support status when fewer than 2 groups are available
- internally calls `frontend_facade.execute_compare_request()` which routes through unified execution
- route layer serializes through `present_compare_response()`
- `CompareService` now attempts an LLM-backed structured comparison first; if the runtime is unavailable, returns unusable output, or produces invalid JSON, it falls back to the original heuristic compare
- evidence IDs in the LLM response are mapped back to retrieved chunks so citations remain traceable

Response:

- `query`
- `common_points` — structured comparison points where documents agree
- `differences` — structured comparison points where documents diverge
- `conflicts` — structured comparison points where documents contradict
- `support_status` — overall grounding quality (`supported`, `insufficient_evidence`, `partially_supported`, `conflicting_evidence`)
- `refusal_reason` — present only when support_status indicates a refusal
- `citations` — evidence citations for each comparison point
- `retrieved_count`

Note: compare results also appear in the unified execution response at `compare_result` and in the `compare.v1` structured artifact. Both `/compare` and `/frontend/execute` return the same core compare contract.

### `POST /frontend/execute`

Request (via `UnifiedExecutionRequestBody`):

- `task_type: "chat" | "summarize" | "compare" | null` — optional; omit or send `null` to enable auto-detection
- `user_input` — the user's query or instruction
- `top_k`
- `filters`
- `output_mode`
- `citation_policy`
- `task_options`

Behavior:

- when `task_type` is omitted or `null`, a rule-based `IntentClassifier` inspects `user_input` for compare/summarize keywords and selects the most likely task type
  - strong compare keywords: 比较, 对比, 区别, 差异, 异同, compare, comparison, difference, contrast, versus, vs, …
  - strong summarize keywords: 总结, 概括, 归纳, 摘要, summarize, summary, recap, outline, …
  - if no keyword matches, defaults to `chat` with confidence 0.5
  - confidence levels: strong match = 0.9, weak match = 0.65, fallback = 0.5
- when `task_type` is explicitly provided, the classifier records `user_override=True` and preserves the requested type
- after intent classification, the existing `_route_chat_summary_request` logic can still re-route `chat` → `summarize` based on summary phrases
- intent metadata (`detected_intent`) is appended to `workflow_trace` in the response metadata, including `task_type`, `confidence`, `reason`, `matched_keyword`, and `user_override`

Response:

- `task_type` — the task type that was actually executed (may differ from the auto-detected value if routing re-routed it)
- `artifacts` — primary result artifact(s) depending on task type
- `citations` — evidence citations
- `metadata.workflow_trace.detected_intent` — intent classification details when auto-detection was used

### `POST /frontend/execute` with `task_type=compare`

Request (via `UnifiedExecutionRequestBody`):

- `task_type: "compare"`
- `user_input` — the comparison question
- `top_k`
- `filters`
- `output_mode: "structured"`

Behavior:

- routes through `FrontendFacade.execute()` which calls `build_execution_plan(TaskType.COMPARE)`
- the plan includes: retrieve → rerank → compress → format_compare_output
- returns `UnifiedExecutionResponse` with:
  - `compare_result` — top-level `GroundedCompareResult`
  - `artifacts` — includes a `compare.v1` `StructuredJsonArtifact`
  - `citations` — evidence citations

Response fields for compare:

- `task_type: "compare"`
- `compare_result` — same structure as the direct `/compare` response
- `artifacts[].kind == "structured_json"` with `schema_name == "compare.v1"`
- `artifacts[].metadata.compare_result` — mirrors `compare_result` for replay/event projection
- `citations` — evidence citations

Both `/compare` and `/frontend/execute?task_type=compare` return the same `compare_result` structure. The unified execute additionally wraps it in a `compare.v1` artifact and adds execution metadata.

## Unified Retrieval Pipeline

CHAT and SUMMARIZE tasks share a single `RetrievalPipeline` backed by LangGraph.

Current graph shape:

```text
START -> retrieve -> rerank -> compress -> quality_check
  quality_ok or max_retries reached -> END
  insufficient and retry available -> query_expand -> retrieve …
```

### quality_check rules (deterministic)

- **chat**: fails if `hits` is empty or `compressed_hits` is empty. One good hit is acceptable.
- **summarize**: fails if `hits` is empty, `compressed_hits` is empty, or `len(compressed_hits) < 2` when `len(hits) > 1`.
- **weak retrieval**: `low_confidence` is set when all distance values are present and `>= 1.5`. This does not alone trigger retry.
- No source-diversity check is applied.
- No compare-specific rules are applied.

### query_expand rules (deterministic, one retry only)

- `max_retries = 1` for this phase.
- Instruction words are stripped from the query: 总结, 概括, 归纳, 摘要, 提炼, 梳理, 比较, 对比, 区别, 差异, 异同, summarize, summary, recap, outline, compare, comparison, difference, differences, contrast, versus, vs.
- Whitespace and punctuation are normalized.
- `top_k` is increased modestly: `retry_top_k = min(max(top_k + 3, int(top_k * 1.5)), 20)`.
- Filters are preserved unchanged.
- No LLM is used for expansion.

### Event behavior

- No-retry path preserves the existing stable event order:
  `retrieval_started → retrieval_completed → rerank_completed → compress_completed → retrieval_pipeline_completed`.
- Retry path emits the same stage events for each attempt, then one final `retrieval_pipeline_completed`.
- `quality_check` and `query_expand` node completions do not emit separate trace events.

### Low-confidence warning

If the pipeline finishes with `low_confidence=True` or with insufficient evidence after the retry is exhausted, a `WARNING_EMITTED` event is surfaced and the warning is appended to response metadata.

### Compare path

COMPARE does **not** use the unified retrieval pipeline. It continues to rely on its own internal retrieval path.

## Shared Filters

Current supported filter fields:

- `source`
- `source_type`
- `section`
- `title_contains`
- `requested_url_contains`
- `page_from`
- `page_to`

Current semantics:

- `source`: single string or list of strings
- `source_type`: single string or list of strings
- `section`: exact match
- `title_contains`: controlled case-insensitive substring match
- `requested_url_contains`: controlled case-insensitive substring match
- `page_from` / `page_to`: inclusive range bounds

Current limits:

- no nested boolean expressions
- no arbitrary field names
- no general regex or fuzzy matching

## Citation Semantics

Citation output remains API-compatible, but is now built from `CitationRecord`.

Important rule:

- if a chunk was compressed for prompting, citation still prefers `original_text`
- this keeps citations traceable even when prompt context is shortened

## Validation Errors

Validation errors return HTTP `422` with:

```json
{
  "error": "validation_error",
  "category": "validation_error",
  "detail": "...",
  "request_id": "..."
}
```

Examples:

- blank `query`
- missing summarize `query/topic`
- ingest URL without `http://` or `https://`
- invalid page range such as `page_from > page_to`

## Service Errors

Service errors return:

```json
{
  "error": "search_error | chat_error | summarize_error | ingest_error",
  "category": "search_error | chat_error | summarize_error | ingest_error",
  "detail": "...",
  "request_id": "..."
}
```

The `request_id` is for log correlation.

`category` currently mirrors `error`. It is an additive field for clients that want an explicit classifier without inferring semantics from the older `error` field alone.

## Response Boundary

The API boundary is now split deliberately:

- internal route code calls the frontend/application facade
- orchestrators call services and return formal service result objects
- `app/api/presenters.py` converts those objects to outward-facing response schemas
- route handlers remain responsible only for request validation, service invocation, and returning schema instances

This keeps compatibility while avoiding route-local dict assembly.

## Service Result Boundary

Current presenter inputs are:

- `SearchServiceResult`
- `ChatServiceResult`
- `SummarizeServiceResult`
- `CompareServiceResult`
- `IngestServiceResult`

This matters because API routes no longer need to know whether a use case internally used:

- retrieval hits
- grouped document evidence
- partial ingest failures
- insufficient-evidence fallbacks

Those concerns are now expressed once in the service result and then mapped by the presenter.

Current route flow:

```text
request schema
  -> frontend/application facade
  -> service result
  -> presenter
  -> response schema
```

Internal consumer rule:

- API routes and external HTTP clients use presenters/response schemas
- demo/eval/scripts should consume service results directly unless they are intentionally testing the HTTP boundary

For future frontend work:

- prefer the application facade/orchestrator layer over direct service wiring
- keep route handlers as thin HTTP adapters over that layer

The same rule applies to source-management commands:

- CLI/service paths consume catalog/lifecycle service results directly
- HTTP endpoints expose response schemas only
- source inspect follows the same split: internal consumers use `SourceInspectServiceResult`; HTTP uses `SourceChunkPageResponse`

## Compatibility Notes

- endpoint paths are unchanged
- ingest response remains JSON-compatible
- search response remains JSON-compatible
- chat/summarize response shapes remain JSON-compatible
- `category` and `partial_failure` are additive response fields
- internal retrieval, ingest, and service layers now use formal result objects instead of dict-heavy protocols
