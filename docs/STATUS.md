# Project Status

Last updated: 2026-04-17

## Branch Layout

| Branch | Purpose | Status |
|--------|---------|--------|
| `feat/langchain-integration` | Main development branch | Active |
| `feat/front-matter-rerank-v5` | Experimental retrieval/pipeline exploration | Retained, not default |

**Working assumption:** `feat/langchain-integration` is the authoritative mainline. Experimental branches are not merged into mainline without explicit review.

## Confirmed Working — Mainline as of 2026-04-16

### Backend Core
- FastAPI service startup (`GET /`, `GET /health`)
- Local file ingest for `.md`, `.txt`, `.pdf` (Chroma persistence)
- URL/HTML ingest (`POST /ingest`) with og:title/og:description/og:image/canonical/domain metadata extraction
- Shared source loader registry (`SourceLoaderRegistry`): `FileSourceLoader` (file) and `URLSourceLoader` (url) share the same `SourceLoader` interface; after `load()` both feed into the same `_build_chunk_documents() → embed → Chroma upsert` pipeline
- **Multi-source ingestion**: file and URL sources are equivalent citizens in the vector store and participate in unified retrieval/citation without any source-type-specific code paths
- Grounded `/search`, `/chat`, `/summarize`, `/compare` endpoints
- Shared retrieval pipeline (retrieve → rerank → compress)
- Citation-aware response generation
- Mermaid and structured JSON output
- Incremental maintenance (create / modify / delete / move)
- No-key local fallback mode

### Unified Execution API (frontend-facing)
- `POST /frontend/execute` — single-shot unified execution with full response
- `POST /frontend/execute/stream` — SSE projected event stream
- `GET /frontend/runs/{run_id}/events` — run replay
- `GET /frontend/skills` — skill catalog listing
- `GET /frontend/skills/{skill_id}` — skill schema detail
- All routes return structured error shapes (422 for validation, 500 for internal)

### Runtime Configuration (Phase 1–3, complete)
- User-configurable OpenAI-compatible runtime via Settings UI
- `api_key` never written to disk (`api_key_source: "env" | "none"` marker only)
- `LLM_API_KEY`, `LLM_RUNTIME_BASE_URL`, `LLM_RUNTIME_MODEL` env vars set on save
- `config_source` field in responses: `active_config_env | active_config_disabled | env_override | default`
- Model override correctly propagates to `ChatOpenAI` and `OpenAICompatibleLLM` at runtime
- Bootstrap from saved config on server restart (key must be re-entered)

### Frontend
- React + TypeScript + Vite SPA
- Split-pane workspace: left document pane, right agent pane
- SSE consumption via `fetch` + `ReadableStream` (not EventSource POST)
- Zustand store (`useAgentStore`) drives all UI state
- Artifact rendering: `text`, `mermaid`, `structured_json`, `skill_result`
- Progress phase display: `resolving_runtime | retrieving | generating | finalizing`
- Settings UI: runtime config save / test / reset
- URL ingest UI: "+ Add URL" button in Document Workspace header; dialog submits to `POST /ingest { urls }`, refreshes source list on success

## Not Default Priorities (retained, not actively developed)

These are known and accepted but not the current focus:

- **Multi-provider runtime**: Only OpenAI-compatible runtime is configurable. Multiple named providers / profiles are not in scope.
- **Secret manager integration**: `api_key` persistence across restarts is not implemented. Env-first session-only approach is intentional.
- **Skill system**: Functional but marked experimental (`SkillPolicyMode.DISABLED` default). `bullet_normalize` and `echo` skills are registered; skill result artifacts are in the artifact stream.
- **Front matter structured chunking** (`feat/front-matter-rerank-v5`): Experimental pipeline exploration, not merged to mainline.
- **PDF viewer / citation highlight / Mermaid real rendering**: Not in scope unless explicitly requested.
- **Tauri desktop**: Planned but not active.

## Known Limits

- URL fetch extracts og:title/og:description/og:image/canonical/domain metadata; og:title is preferred over `<title>` tag
- Chroma rebuild on Windows is mitigated but not guaranteed under every long-lived process state
- Exact-match metadata filtering is limited compared with richer query languages
- Reranker/compressor remain lightweight heuristics
- Skill system is experimental; `invalid_skill_input` returns 422 but error shape is minimal
- `ingest_status` is `string | null`, not a formal enum
- Frontend has minimal test coverage (1 Playwright smoke test suite, 2 test cases as of 2026-04-16)
- No CI workflow yet

## Suggested Next Priorities (in recommended order)

1. **Main capability / demo loop hardening** — Strengthen the core chat + retrieval + artifact display loop; add more Playwright coverage for the `/frontend/execute/stream` path
2. **Agent / workflow usability** — Improve response quality, citation accuracy, and retrieval precision
3. **Engineering hardening** — CI setup, broader integration test coverage, documentation cleanup

## Quick Verification Commands

```bash
# Backend: skill API tests
conda run -n minddock python -m pytest tests/integration/test_skill_api_routes.py -v

# Backend: runtime config tests
conda run -n minddock python -m pytest tests/integration/test_runtime_config_api.py -v

# Backend: run a focused smoke (any 2+ passing means core routes work)
conda run -n minddock python -m pytest tests/integration/ -k "execute" --tb=no -q

# Frontend: TypeScript check
cd frontend && npx tsc --noEmit

# Frontend: Playwright smoke tests (requires dev server on port 3000)
cd frontend && npx playwright test tests/execute-stream.spec.ts --reporter=line
```
