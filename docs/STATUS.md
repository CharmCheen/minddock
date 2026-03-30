# Project Status

Last updated: 2026-03-30

## Current Stage

MindDock is currently in the MVP stage.

The core backend loop is already runnable:

- local knowledge ingest
- Chroma persistence
- `/search`
- `/chat`
- `/summarize`
- watcher-based incremental maintenance

The project is still being iterated toward a more complete graduation-project backend with better retrieval quality, more stable edge-case behavior, and stronger engineering discipline.

Recommended local/demo environment:

- `conda`
- Python `3.11`
- create from `environment.yml`

## Completed Items

- FastAPI backend startup
- `GET /`
- `GET /health`
- local ingestion pipeline
- `.md`, `.txt`, and `.pdf` ingestion
- Chroma local persistence
- search response with structured citations
- grounded chat response with citations
- grounded summarize response with citations
- watcher-based create / modify / delete incremental update
- fallback local demo path without a remote LLM key
- baseline unit / integration / contract tests in the repository
- short demo command layer via `python -m app.demo ...`
- fixed log directory with info / debug / trace level files under `logs/`

## In Progress

- stabilizing filtered retrieval behavior
- improving rebuild behavior for long-running API mode
- keeping repository documentation aligned with actual code status
- preparing the project for clearer defense/demo presentation
- standardizing local/demo environment usage around conda

## Known Issues

- multi-filter search is brittle and can fail at runtime against the current Chroma query behavior
- `/ingest` with `rebuild=true` can fail in long-running API mode on Windows because Chroma files may be locked
- rerank and compress are still placeholder no-op hooks
- retrieval quality is weaker when the app falls back to `DummyEmbedding`
- real OpenAI-compatible remote provider support exists in code, but local demos may still use the fallback path
- CI workflow is not configured yet

## Next Priorities

1. fix the real runtime issues in search filtering and rebuild mode
2. improve retrieval quality and local demo consistency
3. add URL ingestion
4. replace or narrow the rerank/compress placeholders with a concrete implementation
5. add CI and keep tests easy to run locally
6. continue syncing README, status, and demo docs with code changes

## Documentation Update Rule

Update this file before or immediately after each important push that changes:

- what features are actually working
- what the recommended demo path is
- what issues are currently blocking or partially implemented
- what the next short-term iteration priorities are

This file is intended to be the lightweight project-progress ledger for the repository.
