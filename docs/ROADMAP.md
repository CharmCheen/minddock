# MindDock Roadmap

## Current Phase

`Phase 1: MVP foundation`

Completed:

- Runnable FastAPI backend
- Local document ingestion for `.md` and `.txt`
- Persistent Chroma storage
- Minimal `/search` and `/chat` endpoints
- Domain and port contracts

## Next Milestones

### Phase 2: Retrieval Hardening

- Add metadata filters to search
- Stabilize citation structure and traceability
- Improve error handling for empty or weak evidence
- Add regression coverage for ingest and retrieval

### Phase 3: RAG Quality

- Introduce configurable rerank and compression providers
- Support profile-driven retrieval settings
- Strengthen grounded answer formatting
- Add document deletion and update workflows

### Phase 4: Source Expansion

- Add PDF ingestion
- Add URL/web page ingestion
- Normalize document metadata across sources

### Phase 5: Orchestration

- Add topic summarization workflow
- Add structured outputs such as Mermaid or JSON outline
- Add profile and preference persistence

## Non-Goals For Now

- Multi-tenant deployment
- Public cloud hosting defaults
- Full CI/CD rollout in this repository stage
