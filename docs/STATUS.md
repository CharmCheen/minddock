# Project Status

Last updated: 2026-04-02

## Current Stage

MindDock has completed the first three integration stages and is now in stage 4: system engineering and usability hardening.

The backend is no longer only a runnable MVP. The current focus is:

- reducing double paths and runtime ambiguity
- making ingest and incremental maintenance safer
- improving API error semantics
- strengthening integration tests and engineering documentation

## Confirmed Working

- FastAPI service startup
- `GET /`
- `GET /health`
- local file ingest for `.md`, `.txt`, `.pdf`
- URL / HTML ingest through `POST /ingest` or `python -m app.demo ingest --url ...`
- Chroma persistence
- grounded `/search`, `/chat`, `/summarize`
- shared citations for search/chat/summarize
- watcher-based incremental create / modify / delete / move maintenance
- LangChain-first service/runtime path
- no-key fallback local mode
- heuristic rerank / compression
- basic summarize and map-reduce summarize
- Mermaid structured output

## Stage 4 Improvements Completed

- clarified the formal LLM design into primary LangChain runtime plus explicit compatibility/fallback path
- kept the no-key local path while reducing ambiguity about which path is preferred
- added minimal URL ingest with HTML text extraction and URL-preserving metadata
- changed batch ingest to isolate per-source failures instead of failing the whole run on the first bad input
- changed repeated ingest and incremental update to replace stale chunk IDs reliably
- reduced Windows rebuild failures by releasing cached vector-store state and retrying directory cleanup
- added shared validation-error JSON responses
- aligned `source`, `section`, `source_type` filter handling across search/chat/summarize
- added integration tests for end-to-end ingest/search/chat/summarize, URL ingest, repeat ingest consistency, watcher moves, and provider fallback

## Remaining Known Limits

- URL parsing is intentionally minimal and will miss some complex sites
- Chroma rebuild on Windows is mitigated, not guaranteed under every long-lived process state
- exact-match metadata filtering is still limited compared with richer query languages
- reranker/compressor remain lightweight heuristics
- no CI workflow yet

## Current Priorities

1. improve URL extraction quality with a stronger replaceable parser
2. keep expanding high-value integration coverage around rebuild, file locks, and corrupted PDFs
3. improve retrieval quality beyond the current heuristic post-processing
4. decide whether to expand the LangGraph workflow beyond retrieval/context preparation
5. add CI and environment-stable regression checks
