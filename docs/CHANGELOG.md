# Changelog

This file is the active modification log for the repository.
Update it before every push.

## Unreleased

### Added

- LLM-backed grounded compare generation in `CompareService` with evidence-aware structured JSON parsing and heuristic fallback for runtime safety
- `CompareService` now accepts an optional `runtime` and `llm_override`, matching the pattern used by `ChatService` and `SummarizeService`
- COMPARE execution plan now sets `requires_runtime=True` so the unified execution pipeline resolves and injects a runtime profile
- Tests covering LLM JSON parsing, evidence ID mapping, runtime exception fallback, empty-array fallback, and citation preservation for compare
- Open-source governance files: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`
- Project tracking docs: `docs/ROADMAP.md` and `docs/TEST_PLAN.md`
- Baseline automated tests for API routes, schemas, chat service, and contract definitions

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
