# Response Model

## Purpose

This document describes the outward-facing API response models introduced in stage 7.

The goal is not to redesign the API from scratch. The goal is to keep existing response shapes usable while making the boundary between internal domain objects and external JSON explicit and maintainable.

## Boundary Rule

Internal layers may use:

- `IngestBatchResult`
- `SearchResult`
- `RetrievedChunk`
- `CitationRecord`
- other source/retrieval domain objects

Application/service layer now generally returns:

- `IngestServiceResult`
- `SearchServiceResult`
- `ChatServiceResult`
- `SummarizeServiceResult`

The API layer should expose:

- `IngestResponse`
- `SearchResponse`
- `ChatResponse`
- `SummarizeResponse`
- `ErrorResponse`

Conversion happens in:

- `app/api/presenters.py`

This keeps route handlers thin and avoids endpoint-local dict assembly. Response models should generally not need to understand workflow internals directly.

Important boundary rule:

- response models are for outward API contracts
- internal demo/eval/script consumers should prefer service results instead

## Main Success Responses

### `SearchResponse`

Top-level fields:

- `query`
- `top_k`
- `hits`

Each hit includes:

- `text`
- `doc_id`
- `chunk_id`
- `source`
- `source_type`
- `title`
- `section`
- `distance`
- `citation`

### `ChatResponse`

Top-level fields:

- `answer`
- `citations`
- `retrieved_count`
- `mode`

Current `mode` is additive and defaults to `grounded`.

### `SummarizeResponse`

Top-level fields:

- `summary`
- `citations`
- `retrieved_count`
- `mode`
- `output_format`
- `structured_output`

`structured_output` remains a legacy-compatible string field for now.

### `IngestResponse`

Top-level fields:

- `documents`
- `chunks`
- `ingested_sources`
- `failed_sources`
- `partial_failure`

`partial_failure=true` means the request succeeded overall, but at least one source failed.

## Shared Provenance Objects

### `CitationItem`

Fields:

- `doc_id`
- `chunk_id`
- `source`
- `snippet`
- `page`
- `anchor`
- `title`
- `section`
- `location`
- `ref`

This is the shared provenance shape across:

- `/search`
- `/chat`
- `/summarize`

### `FailedSourceItem`

Fields:

- `source`
- `source_type`
- `reason`

This is used only for partial ingest failures.

## Error Response

All handled errors use:

- `error`
- `category`
- `detail`
- `request_id`

Notes:

- `error` is the established machine-readable field
- `category` currently mirrors `error`
- `request_id` supports log correlation
- validation, service, and unexpected errors all use the same outer shape

## Compatibility Notes

The current response-layer work is intentionally additive:

- endpoint paths are unchanged
- existing top-level success fields are preserved
- existing citation structure is preserved
- `category` and `partial_failure` are additive fields
- presenter functions now mainly consume formal service results rather than ad-hoc dicts

## Known Limits

- there is no explicit API versioning layer yet
- `structured_output` is still a plain string rather than a richer typed envelope
- debug/tracing metadata is not yet exposed, but the current schema layout leaves room for additive fields later
