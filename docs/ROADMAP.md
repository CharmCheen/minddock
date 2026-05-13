# MindDock Roadmap

> Status note: this file is a compact current-state roadmap. For defense wording, also see `README.md`, `README_ZH.md`, `docs/thesis-alignment.md`, and `docs/demo-guide.md`.

## Current Phase

`Defense-ready local prototype`

Completed now:

- Runnable FastAPI backend.
- React + Vite frontend in this repository.
- Local document ingestion for `.md`, `.txt`, text-based `.pdf`, `.csv`, image OCR text, and transcript-based audio/video files.
- Static URL / HTML ingestion for fetchable pages.
- Persistent Chroma storage.
- `/search`, `/chat`, `/summarize`, `/compare`, `/ingest`, source lifecycle, and frontend unified execution endpoints.
- Shared retrieval filters for source, source_type, section, title/requested-url contains, and page ranges.
- Traceable citations in search, chat, summarize, and compare responses.
- Incremental maintenance for create / modify / delete / move.
- Frontend runtime configuration, media transcript configuration, SSE run events, replay, and cancellation.
- Trusted-only Source Skill catalog and local manifest registration flow.
- Schedule-candidate extraction as a review workflow.
- Baseline automated tests for the core backend path.
- GitHub Actions CI baseline.

## Next Milestones

### Retrieval Hardening

- Improve retrieval quality evaluation.
- Add stronger regression coverage for ingest and retrieval edge cases.
- Refine evidence selection and fallback behavior.
- Evaluate a true cross-encoder reranker as an optional replacement for heuristic rerank.

### Source Expansion

- Add Word/Docx ingestion.
- Normalize document metadata across sources.
- Explore multimodal image/video understanding beyond OCR and transcript text.

### Orchestration

- Consolidate more retrieval preparation into LangGraph while keeping service-owned citations and guardrails.
- Add production calendar sync only after schedule-candidate confirmation, dedupe, conflict handling, and permission boundaries are designed.
- Add long-term memory or vectorized preference retrieval only after privacy and reset semantics are clear.

## Non-Goals For Now

- Multi-tenant deployment.
- Public cloud hosting defaults.
- Fully autonomous LangGraph Agent controller.
- Third-party plugin marketplace, remote install, signature validation, and sandbox execution.
- Native video-frame understanding in the current media transcript workflow.
- Full production release pipeline beyond the baseline CI workflow.
