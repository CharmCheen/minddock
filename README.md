# MindDock

MindDock is a backend-oriented personal knowledge management assistant built around a grounded RAG pipeline. The current work is focused on making both the ingest side and the retrieval side look like a maintainable program: explicit source identity, formal ingest models, formal retrieval models, controlled filter semantics, and clear service/runtime boundaries.

The latest architecture work also adds:

- a frontend-facing application facade over the main use cases
- a runtime port/adapter model so LangChain is no longer the only architectural center
- a versioned Prompt Profile Registry for grounded chat, summary, and compare prompts
- a trusted-only Source Skill control plane for built-in ingestion capabilities
- a workspace-local user preference profile for lightweight request defaults
- a unified frontend execution API with projected event streaming, run replay, and cancellation
- runtime-editable LLM and media transcript configuration, including optional local ASR support
- a schedule-candidate extraction workflow for turning knowledge-base text into reviewable events
- a CI baseline workflow for the core Python test suite

## Current Scope

Implemented core capabilities:

- local file ingest for `.md`, `.txt`, `.pdf`, `.csv`, image files, and audio/video files
- URL / HTML page ingest with og:title / og:description / og:image / canonical / domain metadata extraction; og:title preferred over `<title>` tag
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
- Prompt Profile Registry metadata in workflow traces
- trusted-only Source Skill catalog/API/settings surface for built-in handlers
- workspace-local user preference profile metadata for default task type, retrieval depth, answer style, and citation strictness
- frontend execution endpoints for task orchestration, server-sent event streaming, run status, event replay, and cancellation
- runtime configuration endpoints for LLM profiles, active runtime overrides, media transcript providers, and local ASR bootstrap/status
- schedule-candidate scan/confirm/dismiss endpoints for lightweight event extraction from indexed text
- GitHub Actions CI baseline that installs the package and runs `scripts/run_ci_baseline.py`

## Thesis / Demo Readiness Snapshot

This repository is ready to support a thesis-defense demo as a local, evidence-first personal knowledge assistant. The safest wording is:

Completed:

- text-based PDF, Markdown, and TXT ingestion
- RAG question-answering loop from ingest to retrieval, generation, citation, and workflow trace
- citation / evidence / source / page / chunk traceability for grounded tasks
- watchdog-based incremental ingest for local source changes
- runtime configuration and runtime adapter boundaries
- Prompt Profile Registry for grounded chat, summary, and compare generation strategies
- trusted-only Source Skill control plane for built-in source handlers
- workspace-local user preference profile for lightweight request defaults
- frontend event-stream execution and run-control flow
- media transcript ingestion through sidecar transcripts, remote OpenAI-style transcription, or optional local ASR
- baseline CI workflow for regression protection

Partially completed:

- static web page body extraction
- CSV rows-as-text ingestion
- OCR text ingestion for images
- audio/video transcript-text ingestion through sidecar files, remote API, or local ASR configuration
- heuristic rerank
- trimming / lexical context compression
- lightweight rule-based intent classification
- schedule extraction as reviewable candidates, not a full calendar integration
- LangGraph retrieval preparation subworkflow

Future work:

- Word/Docx ingest
- complete Skill Market
- remote plugin installation
- plugin signature validation
- sandboxed plugin execution
- OpenAPI / MCP tool import
- long-term user memory
- automatic user profiling
- true cross-encoder reranker
- LLM context compression
- production calendar sync for extracted schedule candidates
- complete LangGraph Agent controller

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

Current built-in file formats and input paths:

- Markdown and plain text are supported as primary text sources
- text-based PDF is supported with page/block metadata where extraction succeeds
- static HTML/URL extraction is supported when the page is fetchable without browser execution
- CSV is ingested as rows-as-text, not as a spreadsheet reasoning engine
- image OCR text ingest is available through mock/disabled modes or RapidOCR when configured; tall images are split before OCR
- audio/video ingest is transcript-text based through sidecar `.transcript.md`, `.transcript.txt`, `.srt`, `.vtt`, remote OpenAI-style transcription, or optional local ASR

Not currently supported as completed capabilities:

- Word/Docx
- JavaScript-rendered web apps, login-only pages, paywalled pages, or general crawling
- spreadsheet formulas, SQL execution, or table reasoning engines
- native multimodal image understanding beyond OCR text
- native audio/video understanding beyond transcript text

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

For future frontend-agent work:

- prefer `/frontend/execute` or `/frontend/execute/stream` for user-facing task execution
- use run-status, replay, and cancellation endpoints instead of long-lived route-local state
- keep runtime and media transcript settings behind the existing frontend configuration endpoints

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

### Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### Call the API

```powershell
python -m app.demo search --query "local Chroma"
python -m app.demo chat --query "How is data stored?"
python -m app.demo summarize --topic "storage design"
python -m app.demo compare --question "Compare the storage approaches across documents"
```

## Defense Demo Shortest Path

1. Start the backend with `python -m app.demo serve` and the frontend with `npm run dev` from `frontend`.
2. Open the source list and show indexed sources.
3. Upload or place documents into the local knowledge base, then run ingest or the watcher.
4. Execute chat, summarize, and compare tasks.
5. Show evidence, citations, source/page/chunk references, and workflow trace metadata.
6. Show or explain Prompt Profile, Source Skill, and User Preference surfaces:
   - Prompt Profile metadata appears in workflow traces for chat, summary, and compare.
   - Settings > Sources shows trusted built-in Source Skills and their limitations.
   - Settings > Retrieval / Display stores workspace-local preference defaults.

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
- `GET /sources/{doc_id}/chunks`
- `GET /sources/by-source?source=...`
- `GET /sources/by-source/chunks?source=...`
- `DELETE /sources/{doc_id}`
- `DELETE /sources/by-source?source=...`
- `POST /sources/{doc_id}/reingest`
- `POST /sources/by-source/reingest?source=...`

### Frontend orchestration endpoints

The frontend-facing application layer exposes:

- `POST /frontend/execute`
- `POST /frontend/execute/stream`
- `GET /frontend/runs/{run_id}`
- `GET /frontend/runs/{run_id}/events`
- `POST /frontend/runs/{run_id}/cancel`
- `GET /frontend/runtime-profiles`
- `GET /frontend/runtime-config`
- `PUT /frontend/runtime-config`
- `POST /frontend/runtime-config/test`
- `POST /frontend/runtime-config/reset`

Media transcript configuration endpoints:

- `GET /frontend/media-transcript-config`
- `PUT /frontend/media-transcript-config`
- `POST /frontend/media-transcript-config/test`
- `POST /frontend/media-transcript-config/reset`
- `GET /frontend/media-transcript-config/local/status`
- `POST /frontend/media-transcript-config/local/start`
- `GET /frontend/media-transcript-config/local/model/status`
- `POST /frontend/media-transcript-config/local/model/preload`

Source Skill and schedule-candidate endpoints:

- `GET /frontend/skills`
- `GET /frontend/skills/{skill_id}`
- `GET /frontend/source-skills`
- `GET /frontend/source-skills/{skill_id}`
- `POST /frontend/source-skills/validate`
- `POST /frontend/source-skills/register`
- `POST /frontend/source-skills/{skill_id}/enable`
- `POST /frontend/source-skills/{skill_id}/disable`
- `GET /frontend/schedule-candidates`
- `POST /frontend/schedule-candidates/scan`
- `POST /frontend/schedule-candidates/{candidate_id}/confirm`
- `POST /frontend/schedule-candidates/{candidate_id}/dismiss`
- `POST /frontend/skills/schedule-extraction/run`

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

Run the CI baseline locally:

```powershell
python scripts/run_ci_baseline.py
```

Run the most relevant stage 6 tests:

```powershell
python -m pytest tests/unit/test_retrieval_models.py tests/unit/test_search_service.py tests/unit/test_chat_service.py tests/unit/test_summarize_service.py tests/integration/test_system_pipeline.py
```

## Known Limits

- URL metadata extraction requires a fetchable, HTML-rendered page; JavaScript-rendered pages and paywalled content are not supported
- filter semantics are controlled and intentionally limited, not a full query language
- vector-store post-filtering may fetch extra candidates when enhanced filters are used
- rerank is heuristic, not a trained cross-encoder reranker
- compression is trimming / lexical context reduction, not LLM context compression
- Source Skill is a trusted-only built-in control plane, not a complete Skill Market
- user preferences are workspace-local request defaults, not long-term memory or automatic user profiling
- LangGraph is used for retrieval subworkflow orchestration, not as a complete autonomous Agent controller
- Chroma rebuild behavior on Windows is mitigated but not fully under application control
- the configured CI workflow is a baseline regression suite, not a full production release pipeline

## License

MIT
