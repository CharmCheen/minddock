# MindDock Roadmap

## Current Phase

`Phase 2: defense-ready MVP`

Completed now:

- Runnable FastAPI backend
- Local document ingestion for `.md` and `.txt`
- Persistent Chroma storage
- Minimal `/search`, `/chat`, and `/summarize` endpoints
- Metadata filters for `source` and `section`
- Traceable citations in chat and summarize responses
- Incremental maintenance for create / modify / delete
- Baseline automated tests for the core backend path

## Next Milestones

### Phase 3: Retrieval Hardening

- Improve retrieval quality evaluation
- Add stronger regression coverage for ingest and retrieval edge cases
- Refine evidence selection and fallback behavior

### Phase 4: Source Expansion

- Add PDF ingestion
- Add URL/web page ingestion
- Normalize document metadata across sources

### Phase 5: Orchestration

- Expand summarization beyond the current minimal flow
- Add profile and preference persistence
- Add structured outputs such as Mermaid or JSON outline

## Non-Goals For Now

- Multi-tenant deployment
- Public cloud hosting defaults
- Frontend UI in this repository stage
- Full CI/CD rollout in this repository stage
