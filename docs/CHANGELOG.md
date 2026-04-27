# Changelog

This file is the active modification log for the repository.
Update it before every push.

## Unreleased

### Added

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
- Open-source governance files: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`
- Project tracking docs: `docs/ROADMAP.md` and `docs/TEST_PLAN.md`
- Baseline automated tests for API routes, schemas, chat service, and contract definitions
- Rule-based `IntentClassifier` that maps user input to `TaskType` via keyword matching (Chinese + English) without LLM inference
- `task_type` is now optional in `UnifiedExecutionRequest`; omitting it triggers auto-detection
- Frontend "Auto" mode: omits `task_type` from the request so the backend infers the best task
- Intent metadata (`detected_intent`) is appended to `workflow_trace` in unified execution responses

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

### Notes

- Stage reports under `docs/reports/` remain unchanged by policy
