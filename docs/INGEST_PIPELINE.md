# Ingest Pipeline

## Goals

The ingest pipeline turns external sources into traceable chunks that can be retrieved, cited, replaced, and incrementally maintained.

Stage 5 priorities:

- reduce internal dict protocols
- make loaders extensible
- unify source metadata and identity semantics
- keep batch and incremental flows on the same conceptual model

## Core Domain Objects

The ingest pipeline now centers on these objects:

- `SourceDescriptor`
- `SourceLoadResult`
- `DocumentPayload`
- `IngestSourceResult`
- `IngestBatchResult`
- `IncrementalUpdateResult`
- `FailedSourceInfo`

The key maintenance rule is:

- object-based contracts inside the ingest pipeline
- dict conversion only at API or compatibility boundaries

## Supported Sources

### Local files

Built-in file support:

- `.md`
- `.txt`
- `.pdf`

### URLs

Built-in remote support:

- HTTP / HTTPS HTML pages

## Loader Responsibilities

### `SourceLoaderRegistry`

Responsibilities:

- register available loaders
- resolve the correct loader for a `SourceDescriptor`
- keep `IngestService` independent from source-specific branching

### `FileSourceLoader`

Responsibilities:

- load local text files
- load PDF text page-by-page
- normalize into `SourceLoadResult`

### `URLSourceLoader`

Responsibilities:

- fetch remote HTML
- normalize title/body text
- attach URL/network metadata
- return `SourceLoadResult`

## Full Ingest Flow

```text
SourceDescriptor
  -> SourceLoaderRegistry
  -> SourceLoadResult
  -> chunking + metadata normalization
  -> DocumentPayload
  -> embeddings
  -> vectorstore.replace_document
  -> IngestSourceResult
  -> IngestBatchResult
```

## Replace Semantics

The service does not append blindly.

Per source:

1. build current payload
2. compute embeddings
3. replace current chunk IDs for that `doc_id`
4. delete stale chunk IDs from previous versions

This preserves repeat-ingest consistency when a document shrinks or changes structure.

## Partial Failure Policy

Batch ingest is source-oriented:

- one broken file should not abort all other files
- one failed URL should not abort successful local ingest
- failures are accumulated as `FailedSourceInfo`
- if every requested source fails, the service raises `IngestError`

## Incremental Flow

`IncrementalIngestService` now returns `IncrementalUpdateResult` for file events.

Flow:

1. validate watched path
2. debounce event
3. compute content hash
4. build current `DocumentPayload`
5. replace vector-store state for that `doc_id`
6. update hash store

Safety rule:

- if payload build fails, old chunks remain intact

## URL Fetch Behavior

URL loading currently uses `httpx` with configurable:

- timeout
- retry count
- retry backoff
- SSL verification
- optional insecure fallback
- User-Agent

Defaults are secure:

- SSL verification enabled
- insecure fallback disabled

If insecure fallback is enabled, a failed SSL request may be retried with certificate verification disabled. This is intended only for constrained local environments and should not be treated as the normal mode.

## Metadata Rules

Shared chunk metadata:

- `doc_id`
- `chunk_id`
- `source`
- `source_path`
- `source_type`
- `title`
- `section`
- `location`
- `ref`
- `page`
- `anchor`

Additional URL metadata:

- `requested_url`
- `final_url`
- `status_code`
- `fetched_at`
- `ssl_verified`

## Extension Path

To add a new source type later:

1. define how to create its `SourceDescriptor`
2. implement a `SourceLoader`
3. register it with `SourceLoaderRegistry`
4. reuse the existing chunking/payload/vector-store path

This avoids rewriting `IngestService` for every new source.
