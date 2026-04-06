# Retrieval Model

## Purpose

This document defines the current formal retrieval model used by MindDock.

It exists to answer:

1. what object shape flows through search/chat/summarize
2. how citations relate to compressed context
3. what filter semantics are currently supported

## Core Objects

### `RetrievalFilters`

Represents the controlled filter set shared by:

- `SearchService`
- `ChatService`
- `SummarizeService`
- vector-store search helpers

Fields:

- `sources`
- `source_types`
- `section`
- `title_contains`
- `requested_url_contains`
- `page_from`
- `page_to`

### `RetrievedChunk`

Represents one normalized retrieval hit.

Key fields:

- `text`
- `original_text`
- `compressed_text`
- `doc_id`
- `chunk_id`
- `source`
- `source_type`
- `title`
- `section`
- `location`
- `ref`
- `page`
- `anchor`
- `distance`
- `rerank_score`
- `retrieval_rank`
- `compression_applied`

For URL-origin content it may also carry:

- `requested_url`
- `final_url`
- `status_code`
- `fetched_at`
- `ssl_verified`

### `CitationRecord`

Represents a traceable citation built from a retrieved chunk.

### `ContextBlock`

Represents prompt-ready evidence assembled from retrieved chunks.

### `SearchHitRecord`

Represents one API-facing search hit:

- retrieved chunk
- bound citation

### `SearchResult`

Represents the search service result before route serialization.

### `GroundedSelectionResult`

Represents the subset of retrieved chunks strong enough for grounded generation.

## Shared Retrieval Flow

```text
query + RetrievalFilters
  -> vectorstore search
  -> RetrievedChunk list
  -> grounded selection
  -> rerank
  -> compress
  -> ContextBlock
  -> chat / summarize / API search response
```

## Compression and Citation Rule

This is the most important consistency rule in the current retrieval model:

- prompting should use compressed text when available
- citations should prefer original text when available

That means:

- `ContextBlock` uses `compressed_text` or `text`
- `CitationRecord` uses `original_text` or `text`

This keeps prompt length controlled without making citations misleading.

## Filter Semantics

### Exact and multi-value

- `source`: single or many
- `source_type`: single or many
- `section`: exact single value

### Controlled contains

- `title_contains`
- `requested_url_contains`

These are case-insensitive substring checks.

### Page range

- `page_from`
- `page_to`

These are inclusive bounds.

## Execution Split

Filter execution is intentionally split:

- vector store applies exact-match-friendly constraints where possible
- retrieval layer applies post-filtering for conditions that are awkward or unsafe to encode directly in Chroma queries

This is a deliberate tradeoff:

- more capability than exact match only
- less complexity than a custom DSL or planner

## Current Limits

- no arbitrary metadata field filtering
- no regex matching
- no nested boolean expressions
- no weighted filter ranking
- post-filtering may require retrieving extra candidates first
