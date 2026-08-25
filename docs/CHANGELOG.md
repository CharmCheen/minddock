# Changelog

This file is the active modification log for the repository.
Update it before every push.

## Unreleased

### Documentation

- PRD upgraded to v1.1 (`docs/PRD_可验证文献工作台_v1.1.md`, renamed from v1.0):
  added revision history, appendix C implementation-status matrix mapping every
  FR to its commit with remaining gaps and honest deviations (FR-3b flag-off,
  FR-9 delivered early, self-check LLM layer sequencing), annotated appendix B
  open questions as resolved/open, and recorded milestone progress against the
  M1–M3 plan.

### Added — Verifiable Literature Workbench (PRD `docs/PRD_可验证文献工作台_v1.1.md`)

- **FR-1 Evidence-sufficiency badge** (`app/application/evidence_badge.py`):
  deterministic mapping over existing signals only (support_status,
  low_confidence, quality_reasons, trace_warnings, mock/fallback flags) into
  green/yellow/red/unknown levels; attached to chat/summarize/compare text
  artifacts as `evidence_badge` metadata and rendered as an "Evidence:" chip
  in the frontend. Compare runs degrade to `unknown` until pipeline-style
  quality fields exist. No numeric thresholds before the 50-case eval set.
- **FR-2 Citation self-check** (`app/services/citation_self_check.py`):
  two-layer per-citation verification — a synchronous rule layer (structural
  validity + lexical alignment with conservative thresholds) plus one bounded
  LLM layer (NLI-style three-state verdicts; skipped without runtime; failures
  degrade to rule results). Report attaches as `citation_self_check` artifact
  metadata, summarizes into workflow_trace, streams after the answer via a new
  `verification_completed` internal event projected to an `info` client event.
  Unsupported citations render grayed with a "Not supported" chip in the UI.
- **Run-trace archive** (`app/application/run_trace_archive.py`): best-effort
  JSON persistence of workflow traces/badges/self-checks under
  `data/run_traces/` (gitignored); new read-only endpoints
  `GET /frontend/traces` and `GET /frontend/traces/{run_id}` so verification
  reports survive backend restarts.
- **FR-3 Academic metadata + filters** (`app/rag/frontmatter_metadata.py`):
  ingest-time extraction of `doc_authors` / `doc_year` for eligible file
  sources (pdf/md/txt; media/csv excluded); `MetadataFilters` and
  `RetrievalFilters` gained `authors` / `year_from` / `year_to`; year ranges
  compile into Chroma `$and` operator conditions while authors use inflated
  candidate fetch + case-insensitive substring post-filtering.
- **FR-4 Citation export** (`app/services/citation_export_service.py`):
  BibTeX / GB-T 7714 / APA formatters with explicit missing-field degradation;
  new endpoint `POST /frontend/citations/export`; frontend footer buttons copy
  formatted references to the clipboard.
- **FR-6 Compare quality signals** (`build_compare_quality_trace`):
  compare results now derive pipeline-style quality fields so evidence badges
  apply the full mapping and citation self-check covers compare outputs.
- **FR-3b Frontmatter-aware rerank port** (`app/rag/frontmatter_rerank.py`):
  production adaptation of the experiment's `soft_rerank_v4_frontmatter` role
  bonus/penalty layer on top of the heuristic base score; gated behind the new
  `frontmatter_rerank_enabled` setting (default off) until the multi-document
  regression harness reports a baseline (PRD: 先泛化验证再上线). Query-intent
  extraction, page-1 role classification, and per-intent bonuses are ported
  verbatim; unit tests cover intent detection, role classification, promotion,
  and no-op behavior for non-front-matter queries.
- **FR-9 Schedule .ics export** (`app/services/schedule_ics_service.py`):
  RFC 5545 calendar export at `GET /frontend/schedule-candidates/export.ics`
  (status filter: confirmed/pending/dismissed/all); timed and all-day events,
  text escaping, default one-hour duration, evidence/source in DESCRIPTION.
  Closes the schedule-candidate review loop without OAuth or write access.

### Fixed

- Frontend build blocker: `useAvailabilityStore` was missing the required
  `onlineTimer: null` initial property.

### Documentation

- Added `docs/PRD_可验证文献工作台_v1.0.md` defining the differentiation
  strategy ("answers that verify themselves"), P0 scope, revised milestones,
  decision log from the PM/CTO review, and non-goals.

### Documentation

- Synchronized `README.md`, `README_ZH.md`, and core `docs/` guidance with the current implementation:
  frontend unified execution/run control, runtime and media transcript configuration, Local ASR provider boundaries,
  Source Skill endpoints, schedule-candidate extraction, and the GitHub Actions CI baseline.
- Replaced outdated roadmap/test-plan wording that described early MVP scope or missing CI with current defense-ready
  project boundaries and focused validation commands.

### Fixed

- Reworked `start.bat` into a fail-fast one-click Local ASR demo launcher:
  checks `minddock` and `local-asr`, verifies `faster_whisper` import, requires
  local `models/faster-whisper-base` files, starts Local ASR and backend, saves
  the Local ASR provider config, preloads `base / auto / int8`, waits for model
  `ready`, starts the frontend, opens the browser, and writes startup logs.
- Kept ingest out of `start.bat`; `run_demo_ingest.bat` remains the explicit
  real-ingest workflow and checks backend health, Local ASR health, and model
  readiness before asking for user confirmation.
- Documented that Preload Model does not transcribe, ingest is the first real
  transcription step, smoke tests should prefer `.wav`/`.mp3` before `.mp4`,
  and faster-whisper model weights under `models/` must stay untracked.
- Added startup connectivity checks so `start.bat` only reports ready after
  backend business APIs and the frontend Vite proxy can reach `/sources` and
  `/frontend/media-transcript-config`; expanded the Vite proxy to cover the
  main chat/search/summarize/compare API routes.
- Guarded `run_demo_ingest.bat` against rebuild ingest while the backend is
  still listening on port `8000`, because the running backend can lock
  `data/chroma/chroma.sqlite3`; the script now asks the user to close backend,
  prints manual `netstat`/`taskkill` guidance, rechecks the port, and refuses to
  ingest if the lock risk remains.
- Clarified Local ASR smoke guidance: `start.bat` only starts the stack to
  Ready, rebuild ingest recreates Chroma, backend should be closed before
  `run_demo_ingest.bat`, and the first real ASR smoke test should use a fresh
  English-name `.wav` such as `knowledge_base/local_asr_smoke.wav` instead of
  very short, silent, damaged `.mp4` files or Chinese filenames.
- Extended one-click startup to launch the existing `python -m app.demo watch`
  incremental watcher after Local ASR model readiness. Startup now waits for a
  watcher readiness marker, so the script only reports Ready after the initial
  non-rebuild `knowledge_base` sync has completed and the observer is running.
- Added watcher readiness signaling (`--ready-file`) and a startup-safe
  `--fail-on-sync-error` option so demo startup does not silently ignore
  failed incremental syncs.

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
- **Local ASR provider mode** for Media Transcript Provider: manages a standalone `local_asr_server` (faster-whisper) via health-check + subprocess auto-start
- New provider options: `disabled | mock | api | local`
- Local ASR configuration fields: `local_asr_server_path`, `local_asr_host`, `local_asr_port`, `local_asr_model`, `local_asr_device`, `local_asr_compute_type`, `local_asr_auto_start`, `local_asr_timeout_seconds`
- `ensure_local_asr_if_enabled` bootstrap with `/health` polling and fallback to mock on failure
- `local-dev-key` internal placeholder for local OpenAI-compatible endpoint; no real API key required
- Sidecar transcript priority preserved for all providers including local
- Tests: `test_local_asr_bootstrap.py` (12 tests), extended `test_media_transcript_config_api.py` (local GET/PUT/TEST/RESET), extended `test_media_loader.py` (local provider resolution, fallback, sidecar priority)

- **Local ASR Model Preload and Ready Status**
  - `local_asr_server` 新增 `GET /v1/models/status` 和 `POST /v1/models/preload`，支持后台模型加载与状态查询
  - MindDock 后端新增代理端点：
    - `GET /frontend/media-transcript-config/local/model/status`
    - `POST /frontend/media-transcript-config/local/model/preload`
  - 新增 schema：`LocalAsrModelStatusResponse`、`LocalAsrModelPreloadRequest`
  - `local_asr_bootstrap.py` 新增 `check_local_asr_model_status()` 和 `preload_local_asr_model()` helper
  - 前端 Settings → Media Transcript Provider 在 `provider=local` 区域新增：
    - **Check Model** 按钮 — 查询模型加载状态
    - **Preload Model** 按钮 — 触发后台模型预加载
    - Model Status 结果展示块（Ready / Loading / Not Loaded / Failed）
    - 推荐操作流程提示文案
  - 前端新增类型 `LocalAsrModelStatusResponse`，service 新增 `checkLocalModelStatus()` 和 `preloadLocalModel()`
  - 后端测试：单元测试 4 个（model status + preload），集成测试 12 个（status 6 个 + preload 6 个）
  - 前端 build + smoke tests 通过
  - 文档更新：`docs/LOCAL_ASR_PROVIDER.md`、`docs/VIDEO_SKILL_DEMO.md`、`docs/CHANGELOG.md`

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

- **Media Transcript Config Phase 2 (Frontend Editor)**
  - Frontend Settings page now exposes an editable **Media Transcript Provider** editor (replaces the read-only status card).
  - Form fields: provider (mock/api/disabled), enabled toggle, base_url, api_key (password input, never displayed after save), model, timeout.
  - Save persists non-secret fields to `data/active_media_transcript.json`; api_key is stored only in `os.environ`.
  - Reset removes the active config file and clears UI-set env vars.
  - Test Config button sends the current form values to `POST /frontend/media-transcript-config/test`.
  - New frontend types: `MediaTranscriptConfigUpdateRequest`, `MediaTranscriptConfigTestResponse`.
  - New frontend service methods: `updateConfig`, `resetConfig`, `testConfig`.

- **Media Transcript Config Phase 3 (Media Loader UI Override)**
  - `app/rag/media_loader.py` now resolves effective media transcript config with priority: UI active config > Settings > os.environ > defaults.
  - New `ResolvedMediaTranscriptConfig` frozen dataclass holds the resolved effective config.
  - New `_resolve_media_transcript_runtime_config()` reads the active config file and settings to produce the resolved config.
  - `build_media_transcription_client()` uses the resolved config to construct the appropriate client.
  - `OptionalApiMediaTranscriptionClient` now accepts config as instance fields (`api_key`, `api_base_url`, `model`, `timeout_seconds`) instead of reading from `get_settings()`.
  - Sidecar transcript priority is preserved regardless of provider setting.
  - Provider=mock/disabled behavior unchanged.
  - Tests updated to use dual monkeypatch pattern (media_loader.get_settings + active_config.get_active_media_transcript_config).
  - New Phase 3 tests: UI override uses override values, UI override priority over settings, api_key from os.environ, api_key empty when no env var.

### Fixed

- **Local ASR demo workflow stabilization**
  - `local_asr_server` now supports local model directory overrides:
    `LOCAL_ASR_MODEL_BASE_PATH`, `LOCAL_ASR_MODEL_SMALL_PATH`, and
    `LOCAL_ASR_MODEL_MEDIUM_PATH`.
  - Model preload and transcription now share the same model/device/compute
    cache key, with demo defaults aligned to `base` / `auto` / `int8`.
  - Local ASR failures no longer fall back to mock transcripts; failures return
    an empty local transcript with `local_asr_*` warnings so demo ingest does
    not index placeholder text as real ASR.
  - `start.bat` now fails fast when Local ASR, backend, config save, preload, or
    model readiness fails; frontend build is skipped by default for faster demo
    startup.
  - Added `run_demo_ingest.bat` as a separate explicit ingest step after Local
    ASR is Ready.
  - Documentation clarifies the two-environment setup, local model path
    behavior, startup responsibilities, and wav/mp3-first smoke test guidance.

- **Media Transcript Config: base_url round-trip** (`P1`):
  - `MediaTranscriptConfigResponse` now includes `base_url: str` so the frontend can round-trip the configured URL.
  - `GET /frontend/media-transcript-config` returns the effective base URL (ui_override or environment).
  - Frontend Settings `loadConfig` now restores the `base_url` form field from the backend response instead of always clearing it.
  - Users can Save → reopen Settings → base_url is preserved → Save again without losing the URL.

- **Media Transcript Config: Phase 3 text and reset boundary** (`P2`):
  - Frontend Settings text updated: "Saved UI configuration is now used by media ingestion."
  - Reset boundary note added: "Reset clears the UI override and current backend-session key."
  - `docs/VIDEO_SKILL_DEMO.md` updated with reset boundary behavior.

- **Progressive SSE Streaming** (`/frontend/execute/stream`): 
  - `RunRegistry.append_internal_event` now real-time projects internal events into `recent_client_events` when `stream_mode` is set, enabling the SSE endpoint to yield events while the run is still executing instead of batching them after completion.
  - `FrontendFacade.execute_run` accepts an optional `on_run_started` callback so the streaming route can obtain the `run_id` immediately and begin polling the registry progressively.
  - `execute_frontend_task_stream` generator was updated to poll `get_recent_client_events` continuously once the `run_id` is known, with a fallback to `project_run_events` for legacy/mock paths.
  - Added unit tests verifying real-time projection behavior for streaming vs non-streaming runs.

### Notes

- Stage reports under `docs/reports/` remain unchanged by policy
