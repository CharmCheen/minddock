# Catalog Model

## Purpose

This document describes the minimal source catalog and lifecycle model introduced in stage 10.

The goal is to make MindDock manageable as a knowledge-base backend without introducing a separate catalog database or a heavy ORM layer.

## Current Design

The catalog is derived from stored chunk metadata in the vector store.

That means:

- no separate migration system is required
- source identity stays aligned with ingest/search/citation identity
- lifecycle actions operate on the same `doc_id` and `source` already used elsewhere

## Core Objects

### Source-side objects

- `CatalogQuery`
- `SourceCatalogEntry`
- `SourceDetail`
- `DeleteSourceResult`

### Service-side objects

- `CatalogServiceResult`
- `SourceDetailServiceResult`
- `DeleteSourceServiceResult`
- `ReingestSourceServiceResult`

## Source Identity

The catalog uses the same identity rules as ingest and retrieval:

- file source: repository-relative path
- URL source: final resolved URL
- `doc_id`: deterministic hash of `source`

Because of that:

- delete by `doc_id` is stable
- detail by exact `source` is understandable to users
- reingest by `source` can work even after a delete removed the current catalog entry

## Supported Lifecycle Operations

### List

Supported:

- list all indexed sources
- filter by `source_type`
- stable sorting by `source`, `title`, `doc_id`

### Detail

Supported:

- lookup by `doc_id`
- lookup by exact `source`
- representative metadata

### Inspect / chunk preview

Supported:

- lookup by `doc_id`
- lookup by exact `source`
- paginated chunk preview with `limit` / `offset`
- controlled `include_admin_metadata=true` expansion

Inspect returns:

- source summary
- `total_chunks`
- `returned_chunks`
- preview-oriented chunk rows

Each chunk preview is intentionally limited to a readable excerpt rather than a raw dump of the stored chunk body.

### Delete

Supported:

- delete by `doc_id`
- delete by exact `source`

Delete returns a structured result with:

- `found`
- `deleted_chunks`
- target identifiers

### Reingest

Supported:

- reingest file source by `doc_id` or exact `source`
- reingest URL source by `doc_id` or exact `source`

Implementation rule:

- reuse the existing loader/ingest/replace flow
- do not reimplement chunking or vector replacement

## Known Limits

- the catalog is reconstructed from vector-store metadata, so it is only as rich as the stored chunk metadata
- there is no historical audit trail yet
- source inspect currently returns preview rows, not full chunk payload export
- file reingest assumes the current file path under the configured knowledge-base directory
- `include_admin_metadata` is a controlled debug/admin surface, not a permissions system

## Future Evolution

If a stronger catalog is needed later, the likely next step is:

1. keep `source` and `doc_id` semantics unchanged
2. move catalog state into a dedicated persistence layer
3. continue exposing the same service result and response model shapes where practical

That path should be incremental rather than a full redesign.
