# MindDock

MindDock is a backend-oriented personal knowledge management assistant built around a grounded RAG pipeline. The current work is focused on making both the ingest side and the retrieval side look like a maintainable program: explicit source identity, formal ingest models, formal retrieval models, controlled filter semantics, and clear service/runtime boundaries.

The latest architecture work also adds:

- a frontend-facing application facade over the main use cases
- a runtime port/adapter model so LangChain is no longer the only architectural center
- a minimal skill registry skeleton for future tool/skill integration

## Current Scope

Implemented core capabilities:

- local file ingest for `.md`, `.txt`, `.pdf`
- URL / HTML page ingest with configurable network behavior
- persistent Chroma vector storage
- `/search`, `/chat`, `/summarize`, `/compare`, `/ingest`, `/health`
- source catalog / lifecycle endpoints for list, detail, chunk inspect, delete, and reingest
- watcher-based incremental maintenance for create / modify / delete / move
- LangChain-first generation runtime with explicit fallback to local mock mode when no API key is present
- grounded citations shared across search, chat, summarize, and compare
- lightweight rerank / compression, map-reduce summarize, Mermaid structured output
- formal source/ingest models and loader registry
- formal retrieval/citation/filter models shared by search/chat/summarize/compare
- formal API response models and centralized route presenters
- formal service result models for search/chat/summarize/compare/ingest
- demo/eval internal consumers aligned to service results
- frontend-facing orchestrators/facade for query and knowledge-base flows
- runtime registry + runtime request/response adapters
- skill registry skeleton with a minimal example skill

## Formal Models

### Source / ingest side

Core objects:

- `SourceDescriptor`
- `SourceLoadResult`
- `DocumentPayload`
- `IngestSourceResult`
- `IngestBatchResult`
- `IncrementalUpdateResult`
- `SourceCatalogEntry`
- `SourceDetail`
- `DeleteSourceResult`
- `SourceChunkPreview`
- `SourceChunkPage`
- `SourceInspectResult`

### Retrieval side

Core objects:

- `RetrievalFilters`
- `RetrievedChunk`
- `CitationRecord`
- `ContextBlock`
- `SearchHitRecord`
- `SearchResult`
- `GroundedSelectionResult`

These objects keep internal service code off loose dict protocols. API compatibility is preserved by converting them to JSON at route boundaries.

### Response / API side

Core boundary objects:

- `SearchResponse`
- `ChatResponse`
- `SummarizeResponse`
- `IngestResponse`
- `CitationItem`
- `FailedSourceItem`
- `ErrorResponse`

Routes now delegate most response serialization to a dedicated presenter layer instead of hand-assembling dicts per endpoint.

### Service / use case side

Core use-case result objects:

- `SearchServiceResult`
- `ChatServiceResult`
- `SummarizeServiceResult`
- `IngestServiceResult`
- `UseCaseMetadata`
- `RetrievalPreparationResult`

These objects let the service layer return stable application results without forcing route handlers or presenters to understand service-internal dicts.

`app/demo.py` and `app/eval/rag_eval.py` now treat these service results as the primary internal consumer contract. Presenter/response schemas remain reserved for HTTP API boundaries.

More detail:

- [docs/SOURCE_MODEL.md](docs/SOURCE_MODEL.md)
- [docs/RETRIEVAL_MODEL.md](docs/RETRIEVAL_MODEL.md)
- [docs/RESPONSE_MODEL.md](docs/RESPONSE_MODEL.md)
- [docs/SERVICE_MODEL.md](docs/SERVICE_MODEL.md)
- [docs/CATALOG_MODEL.md](docs/CATALOG_MODEL.md)
- [docs/APPLICATION_LAYER.md](docs/APPLICATION_LAYER.md)
- [docs/RUNTIME_MODEL.md](docs/RUNTIME_MODEL.md)
- [docs/SKILL_MODEL.md](docs/SKILL_MODEL.md)

## Source Types

Currently supported source types:

- `file`
- `url`

Current built-in file formats:

- Markdown
- plain text
- PDF

Important source rules:

- `source` is the stable filter/citation identity
- file `source` is repository-relative
- URL `source` is the resolved final URL after redirects
- `doc_id` is derived deterministically from `source`

Management capabilities now built on top of that identity:

- list indexed sources
- inspect indexed source detail
- inspect paginated chunk previews for one source
- delete indexed sources
- reingest a source by `doc_id` or exact `source`

## Integration Guidance

For future frontend work:

- prefer the application facade/orchestrator layer instead of calling low-level services directly
- keep HTTP API routes as thin adapters over that facade
- treat the current LangChain runtime as one adapter behind the runtime port, not as the only possible runtime

For future runtime expansion:

- add a new runtime adapter and register it in the runtime registry
- do not rewrite `ChatService` / `SummarizeService` for each backend

For future skill work:

- register skills through the skill registry
- keep skill invocation outside route-local logic
- prefer orchestrator/runtime composition over ad hoc helper functions

## Retrieval and Filter Semantics

`/search`, `/chat`, `/summarize`, and `/compare` now share the same retrieval/filter model.

Supported filter capabilities:

- `source`: single value or multiple values
- `source_type`: single value or multiple values
- `section`: exact match
- `title_contains`: controlled case-insensitive contains
- `requested_url_contains`: controlled case-insensitive contains
- `page_from` / `page_to`: bounded page range filtering

Current limits:

- this is not a general boolean DSL
- `contains` is intentionally limited to a small set of fields
- complex nested filter expressions are not supported

## Quick Start

### Environment

```powershell
conda env create -f environment.yml
conda activate minddock
```

### Install

```powershell
pip install -e ".[dev]"
```

### Build the index

```powershell
python -m app.demo ingest
```

Add one or more URLs during ingest:

```powershell
python -m app.demo ingest --no-rebuild --url http://example.com
```

Inspect one indexed source with chunk previews:

```powershell
python -m app.demo source-chunks --source notes.md --limit 5 --offset 0
python -m app.demo source-chunks --source https://example.com/final --limit 3 --include-admin-metadata
```

### Start the API

```powershell
python -m app.demo serve
```

### Call the API

```powershell
python -m app.demo search --query "local Chroma"
python -m app.demo chat --query "How is data stored?"
python -m app.demo summarize --topic "storage design"
python -m app.demo compare --question "Compare the storage approaches across documents"
```

## URL Fetch Configuration

Relevant settings:

- `url_fetch_timeout_seconds`
- `url_fetch_retry_count`
- `url_fetch_retry_backoff_seconds`
- `url_fetch_verify_ssl`
- `url_fetch_allow_insecure_fallback`
- `url_fetch_user_agent`

Defaults are intentionally conservative:

- SSL verification is enabled
- insecure fallback is disabled

If insecure fallback is enabled, the loader may retry a failed SSL request without certificate verification. This is useful in constrained local environments, but it is not the safe default.

## API Notes

### `POST /ingest`

Request fields:

- `rebuild`
- `urls`

Response fields:

- `documents`
- `chunks`
- `ingested_sources`
- `failed_sources`
- `partial_failure`

`partial_failure=true` means at least one source failed but the request still completed successfully.

### Shared error shape

Handled API errors use the same top-level fields:

- `error`
- `category`
- `detail`
- `request_id`

`category` currently mirrors `error` and exists as an explicit extension point for future client logic.

### Source lifecycle endpoints

Available management endpoints:

- `GET /sources`
- `GET /sources/{doc_id}`
- `GET /sources/by-source?source=...`
- `DELETE /sources/{doc_id}`
- `DELETE /sources/by-source?source=...`
- `POST /sources/{doc_id}/reingest`
- `POST /sources/by-source/reingest?source=...`

### Shared retrieval filters

The same filter object is accepted by:

- `/search`
- `/chat`
- `/summarize`

Filter execution is split deliberately:

- vector store handles exact-match-friendly constraints
- retrieval layer applies controlled post-filtering for multi-value, contains, and page-range behavior

## Tests

Run the full suite:

```powershell
python -m pytest
```

Run the most relevant stage 6 tests:

```powershell
python -m pytest tests/unit/test_retrieval_models.py tests/unit/test_search_service.py tests/unit/test_chat_service.py tests/unit/test_summarize_service.py tests/integration/test_system_pipeline.py
```

## Known Limits

- URL extraction is still a minimal HTML-body parser
- filter semantics are controlled and intentionally limited, not a full query language
- vector-store post-filtering may fetch extra candidates when enhanced filters are used
- Chroma rebuild behavior on Windows is mitigated but not fully under application control
- no CI workflow is configured yet

## License

MIT
