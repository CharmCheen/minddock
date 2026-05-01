# Changelog

This file is the active modification log for the repository.
Update it before every push.

## Unreleased

### Added

- ASR API provider for media transcript ingestion: `OptionalApiMediaTranscriptionClient` now calls an OpenAI-style `/audio/transcriptions` endpoint via `httpx`
- New configuration fields: `MEDIA_TRANSCRIPT_API_KEY`, `MEDIA_TRANSCRIPT_API_BASE_URL`, `MEDIA_TRANSCRIPT_MODEL`, `MEDIA_TRANSCRIPT_TIMEOUT_SECONDS`
- Graceful fallback from API to mock on missing config, HTTP errors, timeouts, network errors, JSON parse errors, and empty text responses
- API key is never written to metadata, warnings, or logs
- Sidecar transcript priority is preserved regardless of provider setting
- Mock and disabled provider behavior unchanged
- Tests covering API success, missing config fallback, HTTP error fallback, timeout/network error fallback, empty text fallback, JSON parse error fallback, sidecar priority, key leak prevention, endpoint construction, and original mock/disabled behavior

- Rule-based retrieval quality check (`quality_check`) after compress in the unified retrieval pipeline
- One bounded retry (`max_retries = 1`) with deterministic query expansion: instruction-word stripping, whitespace normalization, and modest `top_k` increase (`min(max(top_k + 3, int(top_k * 1.5)), 20)`)
- `UnifiedWorkflowState` extended with `quality_ok`, `quality_reasons`, `low_confidence`, `reflection`, `original_query`, `expanded_query`, `retry_count`, `max_retries`, and `task_type`
- Low-confidence / insufficient-evidence warnings surfaced through `WARNING_EMITTED` events and appended to response metadata
- Fallback `_SequentialGraph` supports the same conditional retry loop when LangGraph is unavailable
- Tests covering sufficient evidence, empty-hit retry, query expansion, top_k bounds, filter preservation, retry ceiling, low-confidence flagging, fallback conditional retry, and LangGraph-compatible fallback stream shapes
- Orchestrator tests verifying `task_type` is passed into the pipeline for CHAT/SUMMARIZE, COMPARE remains unaffected, and warnings are emitted after exhausted retries
- LLM-backed grounded compare generation in `CompareService` with evidence-aware structured JSON parsing and heuristic fallback for runtime safety
- `CompareService` now accepts an optional `runtime` and `llm_override`, matching the pattern used by `ChatService` and `SummarizeService`
- COMPARE execution plan now sets `requires_runtime=True` so the unified execution pipeline resolves and injects a runtime profile
- Tests covering LLM JSON parsing, evidence ID mapping, runtime exception fallback, empty-array fallback, and citation preservation for compare
- Source-scoped two-source compare planning: when `filters.sources` contains exactly 2 sources, `CompareService` retrieves, reranks, and compresses each source independently before building left/right evidence groups; more than 2 sources are limited to the first two with a recorded warning
- Open-source governance files: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`
- Project tracking docs: `docs/ROADMAP.md` and `docs/TEST_PLAN.md`
- Baseline automated tests for API routes, schemas, chat service, and contract definitions
- Rule-based `IntentClassifier` that maps user input to `TaskType` via keyword matching (Chinese + English) without LLM inference
- `task_type` is now optional in `UnifiedExecutionRequest`; omitting it triggers auto-detection
- Frontend "Auto" mode: omits `task_type` from the request so the backend infers the best task
- Intent metadata (`detected_intent`) is appended to `workflow_trace` in unified execution responses
- Compare points now support optional `confidence`, `taxonomy`, and `evidence_coverage` metadata; `confidence` is clamped to `[0.0, 1.0]`, `taxonomy` normalizes to a controlled vocabulary, and `evidence_coverage` is server-computed from resolved evidence counts
- Frontend now surfaces Compare 2.0 point metadata badges and a collapsed "Why this answer?" workflow-trace explanation panel for task, evidence, retry, source-scope, and quality signals.

### Changed

- Repository naming aligned to `MindDock`
- `.gitignore` updated to ignore runtime log files
- `pyproject.toml` now documents development test dependencies and pytest settings
- FastAPI startup logging moved from deprecated `on_event` hook to `lifespan`
- LLM provider contract now consistently uses `query + evidence` across chat providers and service calls
- Mock LLM output was repaired and made readable for no-key `/chat` flows
- Citation metadata now carries traceable fields such as `title`, `section`, `location`, and `ref` through ingest and chat responses
- `/search` and `/chat` now support minimal metadata filters for `source` and `section`, backed by Chroma `where` queries
- Added a minimal `/summarize` endpoint that reuses retrieval, filters, providers, and citations for grounded topic summaries
- Incremental maintenance now has baseline tests and docs covering create, modify, delete, and watcher event forwarding
- README and demo docs were updated to document the current defense-ready flow: ingest -> search -> chat -> summarize -> incremental maintenance
- Added a concise architecture overview and a bundled `knowledge_base/example.md` dataset for fresh-clone demos

### Added

- **Media Transcript Frontend/Backend Alignment**
  - New read-only backend endpoint `GET /frontend/media-transcript-config` exposes sanitized media transcript configuration (enabled, provider, api_key_configured, base_url_configured, model, timeout, capability, limitations, config_source). No API keys are returned.
  - Frontend Settings page now displays a read-only **Media Transcript Provider** status card under the Runtime tab, clearly stating this is transcript-only ASR and not video frame understanding.
  - Source list and source drawer now show transcript provider badges (`Transcript: api` / `sidecar` / `mock` / `disabled`) when `loader_name` is `video.transcribe` or `audio.transcribe`, plus `retrieval_basis: transcript_text`.
  - Integration tests cover the new endpoint (200 response, no API key leak, correct field types, environment reflection).

- **Media Transcript Derived Docs Phase 1 (Backend Only)**
  - New `MediaTranscriptPostprocessor` in `app/rag/media_transcript_postprocessor.py` generates deterministic extractive summary and outline chunks from media transcripts without any LLM calls.
  - New configuration fields (all default-off): `MEDIA_TRANSCRIPT_DERIVED_ENABLED`, `MEDIA_TRANSCRIPT_DERIVED_MIN_CHARS`, `MEDIA_TRANSCRIPT_DERIVED_MAX_INPUT_CHARS`, `MEDIA_TRANSCRIPT_DERIVED_SUMMARY_MAX_CHARS`, `MEDIA_TRANSCRIPT_DERIVED_OUTLINE_MAX_ITEMS`.
  - Hooked into `app/rag/ingest.py` `_build_chunk_documents` (non-page-mode path) so derived chunks are appended after raw `split_text()` chunks for eligible media sources.
  - Eligibility: only `loader_name` of `audio.transcribe` or `video.transcribe` with `transcript_provider` `sidecar` or `api` are processed; `mock` and `disabled` providers are skipped.
  - Derived chunks carry metadata flags `is_derived=true`, `derived_kind=media_summary|media_outline`, `derived_from=transcript`, `derived_basis=transcript_text`, `evidence_basis=transcript_text` while preserving all original media metadata (`loader_name`, `transcript_provider`, `retrieval_basis`, `source_media`, `media_filename`).
  - Postprocessor failures are swallowed with a warning log so ingest never breaks.
  - No frontend changes in Phase 1; frontend badges/preview deferred to Phase 2.
  - Unit tests cover disabled mode, short-text skipping, mock/disabled provider skipping, metadata correctness, summary char limits, outline item limits, max-input truncation, exception safety, and end-to-end ingest integration.

- **Media Transcript Derived Docs Phase 2 (Frontend + Backend Exposure)**
  - Backend `app/rag/vectorstore.py`: `_build_chunk_preview()` now exposes `is_derived`, `derived_kind`, `derived_from`, `derived_basis` in `admin_metadata` for derived chunks; `_build_source_detail()` aggregates `has_derived_summary` and `has_derived_outline` flags in `representative_metadata`.
  - Frontend Source Drawer (`source-drawer.tsx`): new "Derived Content" section displays extractive summary and outline blocks when derived chunks exist, with "Extractive / deterministic" badge and "Derived from transcript" labels.
  - Frontend Source List (`source-list.tsx`): green Summary and Outline badges appear next to the transcript provider badge when derived content is available.
  - No new dependencies, no LLM calls, no video frame analysis. Derived content is strictly extractive/deterministic from transcript text.

### Fixed

- **Progressive SSE Streaming** (`/frontend/execute/stream`): 
  - `RunRegistry.append_internal_event` now real-time projects internal events into `recent_client_events` when `stream_mode` is set, enabling the SSE endpoint to yield events while the run is still executing instead of batching them after completion.
  - `FrontendFacade.execute_run` accepts an optional `on_run_started` callback so the streaming route can obtain the `run_id` immediately and begin polling the registry progressively.
  - `execute_frontend_task_stream` generator was updated to poll `get_recent_client_events` continuously once the `run_id` is known, with a fallback to `project_run_events` for legacy/mock paths.
  - Added unit tests verifying real-time projection behavior for streaming vs non-streaming runs.

### Notes

- Stage reports under `docs/reports/` remain unchanged by policy
