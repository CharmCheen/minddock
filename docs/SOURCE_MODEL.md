# Source Model

## Purpose

This document defines the current source identity and loader model used by MindDock.

It exists to answer three questions clearly:

1. what is a source
2. how is source identity determined
3. how can new source types be added later

## Core Objects

### `SourceDescriptor`

Represents one ingestable source.

Current fields:

- `source`
- `source_type`
- `local_path`
- `requested_source`

Rules:

- `source` is the stable identity used for filtering and `doc_id`
- `source_type` is currently `file` or `url`
- `local_path` is only used for local file sources
- `requested_source` is useful for URLs when redirects change the final `source`

### `SourceLoadResult`

Represents the normalized content returned by a loader:

- resolved descriptor
- title
- plain text
- source-specific metadata

### `DocumentPayload`

Represents the chunked form that is written into the vector store:

- descriptor
- ids
- documents
- metadatas

### `SourceCatalogEntry`

Represents one indexed source aggregated from chunk metadata.

Current fields:

- `doc_id`
- `source`
- `source_type`
- `title`
- `chunk_count`
- `sections`
- `pages`
- `requested_url`
- `final_url`

### `SourceDetail`

Represents a catalog entry plus representative metadata for detail views.

### `SourceChunkPreview`

Represents one readable preview item for source inspection.

Current fields:

- `chunk_id`
- `chunk_index`
- `preview_text`
- `title`
- `section`
- `location`
- `ref`
- `page`
- `anchor`
- `admin_metadata`

### `SourceChunkPage`

Represents one paginated slice of chunk previews:

- `total_chunks`
- `returned_chunks`
- `limit`
- `offset`
- `chunks`

### `SourceInspectResult`

Represents one source detail plus a paginated chunk preview page.

This is the formal object used by admin/debug style inspect endpoints and CLI commands.

## Identity Semantics

### Files

- `source`: repository-relative path such as `notes.md`
- `source_type`: `file`
- `doc_id`: deterministic hash of `source`

### URLs

- `requested_source`: URL requested by the caller
- `source`: final resolved URL after redirects
- `source_type`: `url`
- `doc_id`: deterministic hash of final `source`

This means repeated ingest remains stable as long as the stored `source` remains stable.

It also means lifecycle operations can work in a predictable way:

- delete by `doc_id`
- inspect by `doc_id` or exact `source`
- reingest by exact `source` even after a previous delete

## Citation Semantics

Citation behavior should remain consistent across source types:

- `doc_id`
- `chunk_id`
- `source`
- `snippet`
- `title`
- `section`
- `location`
- `ref`
- `page`
- `anchor`

For URL sources:

- `page` is usually absent
- `ref` usually resolves to title or title+section
- `source_media` is `text`
- `source_kind` is `web_page`
- `loader_name` is `url.extract`
- `canonical_url` and `meta_description` may be present when exposed by the HTML

URL loader warnings are short diagnostics carried in metadata as `loader_warnings`.
They do not become chunk body text and do not affect embedding input.

For CSV sources, the metadata convention is:

- `source_media` is `text`
- `source_kind` is `csv_file`
- `loader_name` is `csv.extract`
- `retrieval_basis` is `csv_rows_as_text`
- `csv_filename`, `csv_columns`, `csv_row_count`, `csv_rows_indexed`
- `loader_warnings` may contain `csv_empty` or `csv_truncated`

## Source Skill Contract

MindDock describes every built-in loader as a **source skill** through `SourceSkillInfo` in `app.rag.source_skill_catalog`. This is a read-only catalog — it does not execute code or invoke LLMs.

Each skill declares:

- `id`, `name`, `kind`, `version`
- `input_kinds` — accepted file extensions or URL
- `output_type` — always `SourceLoadResult`
- `source_media` — `text` | `image`
- `source_kind` — `pdf_file` | `markdown_file` | `text_file` | `web_page` | `image_file`
- `loader_name` — stable identifier such as `url.extract` or `image.ocr`
- `capabilities` — what the skill can do
- `providers` — available backends (e.g. `mock`, `rapidocr`)
- `limitations` — explicit non-goals

### Metadata fields supporting the contract

Loaders populate these fields in `SourceLoadResult.metadata`:

- `source_media` — the media type of the original source
- `source_kind` — the semantic kind of the source
- `loader_name` — which loader produced the result
- `loader_warnings` — comma-separated diagnostics carried into chunk metadata
- `retrieval_basis` — how the source is retrieved later, e.g. `ocr_text` for image OCR
- `ocr_provider` / `domain` / `canonical_url` — provider-specific metadata when applicable

These fields allow the RAG pipeline to remain source-agnostic while still preserving provenance.

## Loader Extension Model

To add a new source type:

1. decide the stable `source` identity
2. define a `SourceDescriptor`
3. implement a `SourceLoader`
4. register it in `SourceLoaderRegistry`
5. describe it in `source_skill_catalog` if it becomes a built-in skill

Examples of future source types:

- `docx`
- `html_file`
- `note`
- `web_clipper`
- `audio` (future skill)
- `video` (future skill)

## Known Limits

- there is no fully generic metadata schema negotiation yet
- public API filters currently expose only `source`, `section`, and `source_type`
- URL identity currently follows the final resolved URL, which may differ from the requested URL
- URL loading supports static HTML extraction only; it does not render JavaScript, crawl links, use login cookies, or bypass anti-bot protections
- the current catalog is derived from vector-store metadata, not a separate transactional database
- source inspect intentionally returns truncated preview text rather than raw full chunk bodies
