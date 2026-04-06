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
