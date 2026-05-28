# MindDock Post-Defense Zoom-Out Audit

> Generated: 2026-05-28 | Read-only source audit (no runtime verification)

---

## 1. Executive Summary

MindDock is a **local-first, evidence-cited RAG assistant** for personal knowledge bases. The codebase shows a well-structured hexagonal architecture (ports/adapters), a clear separation between domain models and application services, and a thoughtful approach to citation grounding. The system has been tested with ~70 test files, has a functional frontend, and includes incremental indexing with watchdog support.

**Key strengths:**
- Clean hexagonal architecture (`domain/`, `ports/`, `adapters/`, `app/`)
- Evidence-first RAG with explicit `GroundedAnswer`, `CitationRecord`, `EvidenceObject` contracts
- Multi-task orchestration (chat/summarize/compare/search) via `FrontendFacade`
- Incremental ingest with hash-based change detection and watchdog debounce
- Runtime config system with mock fallback and profile-based resolution
- Workflow trace visibility through `EventCollector` → `ClientEvent` projection

**Key concerns:**
- Reranker and compressor are heuristic stubs (`rerank_provider="heuristic"`, `compress_provider="trim"`)
- Hybrid retrieval (BM25+RRF) is disabled by default and lacks persistent index
- No RAG quality evaluation pipeline exists despite `app/evaluation/` scaffolding
- Citation correctness is unverified — no citation accuracy benchmark
- `Source Skill` system is over-designed for current scope (trusted catalog vs. marketplace signals)
- Frontend state management mixes concerns (agent store holds events, artifacts, citations, turns)

---

## 2. Current System Boundary

**What MindDock IS:**
- Personal local knowledge base assistant
- Evidence-cited RAG with retrieval → rerank → compress → generate pipeline
- Multi-format document ingestion (PDF, Markdown, TXT, URL, audio/video transcript)
- Incremental indexing with file watching
- OpenAI-compatible LLM runtime with mock fallback
- React/Vite frontend with streaming SSE execution

**What MindDock is NOT (currently):**
- Not a production-grade RAG platform (no evaluation metrics, no A/B testing)
- Not an agent platform (no tool calling chain, no multi-agent orchestration)
- Not a plugin marketplace (Source Skills are declaration-only, not executable extensions)
- Not a multi-user system (single local instance, no auth)
- Not a vector database admin tool (Chroma is used as embedded, not managed)

**Evidence:**
- `app/core/config.py` — single-user settings, no auth fields
- `app/skills/source_registry.py` — `market_boundary="not_a_skill_market"`
- `app/rag/postprocess.py` — `Reranker` uses heuristic, `Compressor` uses trim
- `app/core/config.py:RERANK_PROVIDER="heuristic"`, `COMPRESS_PROVIDER="trim"`

---

## 3. Architecture Map

### 3.1 Product Layer (Frontend)

```
frontend/src/
├── features/agent/          # Chat/Summarize/Compare UI
│   ├── store.ts             # Zustand store (useAgentStore)
│   ├── components/
│   │   ├── agent-panel.tsx
│   │   ├── agent-input.tsx
│   │   ├── agent-message-list.tsx
│   │   ├── citation-list.tsx
│   │   ├── context-bar.tsx
│   │   └── raw-artifact-viewer.tsx
│   └── types.ts
├── features/workspace/      # Source management
│   ├── store.ts
│   └── components/
├── features/settings/       # Runtime config, skill catalog
│   ├── store.ts
│   └── settings-view.tsx
├── lib/api/                 # API client layer
│   ├── client.ts
│   └── services/
│       ├── execution.ts
│       ├── sources.ts
│       ├── runtime-config.ts
│       ├── skills.ts
│       └── schedule-candidates.ts
└── core/types/api.ts        # TypeScript type definitions
```

- Evidence: `frontend/src/features/agent/store.ts` — `useAgentStore` with Zustand
- Evidence: `frontend/src/lib/api/services/execution.ts` — SSE streaming client

### 3.2 API Layer (FastAPI)

```
app/api/
├── routes.py           # All HTTP endpoints
├── schemas.py          # Pydantic request/response models
├── presenters.py       # Service result → API response mapping
├── streaming.py        # SSE event serialization
└── schedule_routes.py  # Schedule-related endpoints
```

**Key endpoints:**
- `POST /chat` — Grounded chat with citations
- `POST /summarize` — Grounded summarization
- `POST /compare` — Grounded document compare
- `POST /search` — Semantic search with citations
- `POST /ingest` — Document ingestion
- `POST /frontend/execute` — Unified execution entrypoint
- `POST /frontend/execute/stream` — SSE streaming execution
- `GET/PUT /frontend/runtime-config` — Runtime configuration
- `GET /frontend/source-skills` — Source skill catalog

- Evidence: `app/api/routes.py` — 40+ route handlers
- Evidence: `app/api/schemas.py` — 2300+ lines of Pydantic models

### 3.3 Application Orchestration Layer

```
app/application/
├── orchestrators.py    # ChatOrchestrator, KnowledgeBaseOrchestrator, SkillOrchestrator, FrontendFacade
├── models.py           # UnifiedExecutionRequest/Response, ExecutionPlan, ExecutionStep
├── events.py           # ExecutionRun, EventCollector, ExecutionEvent
├── client_events.py    # ClientEvent projection for frontend
├── artifacts.py        # TextArtifact, MermaidArtifact, SearchResultsArtifact
├── intent_classifier.py # Intent classification for task routing
└── run_control.py      # RunRegistry for run lifecycle management
```

**Execution flow:**
1. `FrontendFacade.execute_run(request)` — entry point
2. `IntentClassifier.classify()` — resolve task type if omitted
3. `ChatOrchestrator.build_execution_plan_with_skills()` — build step plan
4. `RuntimeResolver.resolve()` — select runtime profile
5. `RuntimeFactory.create(binding)` — create runtime instance
6. Execute base task (retrieve → rerank → compress → generate)
7. Execute skill steps if any
8. Build `UnifiedExecutionResponse` with artifacts + citations

- Evidence: `app/application/orchestrators.py::FrontendFacade.execute_run` — main orchestration loop
- Evidence: `app/application/models.py::ExecutionPlan` — plan with `ExecutionStep` tuple

### 3.4 RAG Layer

```
app/rag/
├── ingest.py               # Document → chunks → Chroma
├── incremental.py          # Hash-based incremental ingest
├── watcher.py              # Watchdog-based file monitoring
├── splitter.py             # Text splitting (token-based)
├── structured_chunker.py   # PDF structured block chunking
├── embeddings.py           # Embedding backend (Qwen3-Embedding-0.6B)
├── vectorstore.py          # LangChainChromaStore wrapper
├── hybrid_retrieval.py     # BM25 + RRF fusion (disabled by default)
├── postprocess.py          # Reranker (heuristic) + Compressor (trim)
├── retrieval_models.py     # RetrievedChunk, CitationRecord, EvidenceObject, GroundedAnswer
├── source_models.py        # SourceDescriptor, Document, SourceState
├── source_loader.py        # SourceLoaderRegistry with format-specific loaders
├── pdf_parser.py           # PDF parsing with structured blocks
├── url_loader.py           # URL fetching with security guards
├── image_loader.py         # Image OCR via RapidOCR
├── media_loader.py         # Audio/video transcript via ASR API
└── source_skills/          # Source skill implementations
    └── csv_skill.py
```

**Retrieval pipeline:**
1. `SearchService.retrieve()` → `HybridRetrievalService.retrieve()`
2. Dense: `LangChainChromaStore.search_by_text()` (Chroma cosine)
3. BM25: `BM25Index.search()` (in-memory, lazy-built from Chroma scan)
4. RRF: `_rrf_fuse()` — Reciprocal Rank Fusion
5. `Reranker.rerank()` — heuristic reranking
6. `Compressor.compress()` — trim-based compression
7. `expand_evidence_windows()` — neighbor chunk expansion for citation windows
8. `build_context()` → `ContextBlock` for prompt assembly

- Evidence: `app/rag/hybrid_retrieval.py::HybridRetrievalService.retrieve` — full hybrid pipeline
- Evidence: `app/rag/postprocess.py` — `Reranker` and `Compressor` with heuristic implementations

### 3.5 Generation Layer

```
app/llm/
├── factory.py              # get_generation_runtime() compatibility bridge
├── mock.py                 # MockLLM for testing
└── openai_compatible.py    # OpenAI-compatible LLM adapter

app/runtime/
├── base.py                 # GenerationRuntime abstract base
├── factory.py              # RuntimeFactory
├── resolver.py             # RuntimeResolver (capability-aware)
├── registry.py             # RuntimeRegistry (adapter registry)
├── profiles.py             # RuntimeProfileRegistry (YAML/JSON profiles)
├── active_config.py        # Active runtime config (UI-managed)
├── adapters.py             # Runtime adapters
└── models.py               # RuntimeProfile, RuntimeCapabilities, ResolvedRuntimeBinding

app/prompts/
├── registry.py             # Prompt profile registry (3 profiles)
└── models.py               # PromptProfile dataclass
```

**Prompt profiles:**
- `evidence_first_chat_v1` — Evidence-first grounded chat
- `grounded_summary_v1` — Grounded summarization (basic/map/reduce)
- `grounded_compare_json_v1` — Grounded two-source comparison

- Evidence: `app/prompts/registry.py::get_prompt_registry()` — 3 built-in profiles
- Evidence: `app/runtime/resolver.py::RuntimeResolver.resolve()` — capability-aware profile selection

### 3.6 Extension Layer

```
app/skills/
├── registry.py         # SkillRegistry with EchoSkill, BulletNormalizeSkill, ScheduleExtractionSkill
├── models.py           # SkillDescriptor, SkillInvocationRequest/Result
├── manifest.py         # Skill manifest validation
├── handlers.py         # Trusted source handlers
├── policy.py           # SkillAccessEvaluator
├── source_binding.py   # Source skill binding resolution
├── source_registry.py  # SourceSkillRegistry (trusted catalog)
└── local_store.py      # Local skill store
```

- Evidence: `app/skills/registry.py` — 3 registered skills (echo, bullet_normalize, schedule_extraction)
- Evidence: `app/skills/source_registry.py` — `SourceSkillRegistry` with `market_boundary="not_a_skill_market"`

### 3.7 Testing & Engineering

```
tests/
├── unit/               # 60+ unit test files
├── integration/        # 7 integration test files
└── contract/           # 1 contract test file

eval/
├── benchmark/sample_eval_set.jsonl
├── eval_cases_v3.json
└── chunking_eval_report_v4.md, v5.md
```

- Evidence: `tests/unit/` — covers chat_service, compare_service, summarize_service, citation, hybrid_retrieval, incremental_ingest, watcher, etc.
- Evidence: `eval/benchmark/sample_eval_set.jsonl` — exists but no automated runner found

---

## 4. End-to-End Execution Path

### Chat Request Flow

```
Frontend (SSE) → POST /frontend/execute/stream
  → UnifiedExecutionRequestBody.to_application_request()
  → FrontendFacade.execute_run(request)
    → IntentClassifier.classify() — resolve task type
    → ChatOrchestrator.build_execution_plan_with_skills() — build plan
    → RuntimeResolver.resolve() — select runtime profile
    → RuntimeFactory.create(binding) — create runtime
    → RetrievalPipeline.run() — shared retrieval for chat/summarize
      → SearchService.retrieve()
        → HybridRetrievalService.retrieve()
          → LangChainChromaStore.search_by_text() — dense
          → BM25Index.search() — lexical (if enabled)
          → _rrf_fuse() — fusion
      → Reranker.rerank() — heuristic
      → Compressor.compress() — trim
    → ChatService.chat(query, precomputed_hits)
      → select_grounded_hits() — filter by distance threshold
      → assess_evidence_query_alignment() — query/evidence gate
      → expand_evidence_windows() — neighbor expansion
      → build_context() → ContextBlock
      → runtime.generate(RuntimeRequest) — LLM call
      → detect_model_refusal() — post-generation gate
      → build_citation() + build_evidence() — citation assembly
      → assess_grounding() — support status classification
    → ArtifactBuilder.build_chat_artifacts()
    → EventCollector → ClientEvent projection
  → StreamingResponse (SSE)
```

- Evidence: `app/api/routes.py::execute_frontend_task_stream` — SSE endpoint
- Evidence: `app/application/orchestrators.py::FrontendFacade.execute_run` — orchestration
- Evidence: `app/services/chat_service.py::ChatService.chat` — RAG pipeline

---

## 5. Module-Level Findings

### 5.1 Reranker: Heuristic Stub

**Problem:** The reranker is a heuristic based on token overlap scoring, not a trained cross-encoder model.

**Files:**
- `app/rag/postprocess.py` — `Reranker` class
- `app/core/config.py:RERANK_PROVIDER="heuristic"`

**Why this matters:** Heuristic reranking cannot capture semantic relevance. For a thesis project this is acceptable, but for a "usable RAG assistant" this is the single biggest quality bottleneck.

**Impact:** Medium — retrieval quality directly affects answer quality.

**Suggestion:** Add a `cross_encoder` rerank provider option using `sentence-transformers` or `FlashRank`. Keep `heuristic` as default for zero-dependency mode.

**Priority:** P1 | Cost: Medium | Risk: Low

### 5.2 Compressor: Trim-Only

**Problem:** The compressor simply trims chunks to a character limit without semantic compression.

**Files:**
- `app/rag/postprocess.py` — `Compressor` class
- `app/core/config.py:COMPRESS_PROVIDER="trim"`

**Why this matters:** Trim compression loses context at chunk boundaries. For evidence-cited answers, this can cause citation snippets to be incomplete.

**Impact:** Medium — affects citation quality and answer completeness.

**Suggestion:** Add an LLM-based extractive compressor option. Keep `trim` as fallback.

**Priority:** P2 | Cost: Medium | Risk: Low

### 5.3 Hybrid Retrieval Disabled by Default

**Problem:** `hybrid_retrieval_enabled=False` by default. BM25 index is built lazily by scanning all Chroma chunks in memory — no persistent index.

**Files:**
- `app/core/config.py:hybrid_retrieval_enabled=False`
- `app/rag/hybrid_retrieval.py::HybridRetrievalService._ensure_bm25_ready`

**Why this matters:** Pure dense retrieval misses lexical matches (exact terms, acronyms, proper nouns). BM25 helps but the lazy-build approach is O(n) on first query.

**Impact:** Medium — affects recall for lexical queries.

**Suggestion:** Enable by default. Consider persisting BM25 index to disk for faster startup.

**Priority:** P1 | Cost: Low | Risk: Low

### 5.4 No RAG Quality Evaluation Pipeline

**Problem:** `app/evaluation/` has scaffolding (datasets, metrics, runner, reporting) but no automated evaluation pipeline runs. `eval/benchmark/sample_eval_set.jsonl` exists but there's no runner that uses it.

**Files:**
- `app/evaluation/runner.py` — evaluation runner (exists but unused)
- `eval/benchmark/sample_eval_set.jsonl` — eval dataset
- `app/eval/rag_eval.py` — exists but purpose unclear from structure

**Why this matters:** Without evaluation, there's no way to measure whether changes improve or degrade RAG quality.

**Impact:** High — prevents iterative improvement.

**Suggestion:** Create a `make eval` target that runs the evaluation pipeline and produces a report.

**Priority:** P0 | Cost: Low | Risk: Low

### 5.5 Citation Correctness Unverified

**Problem:** Citations are built from retrieved chunks (`build_citation(hit)`) but there's no verification that the cited snippet actually supports the generated answer.

**Files:**
- `app/services/grounded_generation.py::build_citation` — builds citation from hit
- `app/services/grounded_generation.py::assess_grounding` — heuristic support status

**Why this matters:** The model might cite a chunk that was retrieved but doesn't actually support the specific claim in the answer. This is a known RAG failure mode.

**Impact:** High — undermines the "evidence-first" value proposition.

**Suggestion:** Add a citation verification step that checks if the answer claim is entailed by the cited snippet. This is a research-grade improvement.

**Priority:** P1 | Cost: High | Risk: Medium

### 5.6 Source Skill System Over-Designed

**Problem:** The Source Skill system has `SourceSkillRegistry`, `SourceSkillCatalog`, `source_binding`, `local_store`, `manifest`, `handlers` — but only 1 actual skill implementation (`csv_skill.py`). The response schema includes `market_boundary`, `installable`, `remote_install_supported`, `arbitrary_code_execution` fields that signal marketplace intent.

**Files:**
- `app/skills/source_registry.py` — `SourceSkillRegistry`
- `app/rag/source_skills/csv_skill.py` — only implementation
- `app/api/schemas.py::SourceSkillSummaryResponse` — 30+ fields including marketplace signals

**Why this matters:** Over-design creates maintenance burden and misleads contributors about project scope.

**Impact:** Low (functional) / Medium (perception)

**Suggestion:** Simplify to a `SourceHandler` registry with clear "trusted handlers only" documentation. Remove marketplace-sounding fields from the API response.

**Priority:** P2 | Cost: Low | Risk: Low

### 5.7 Runtime Config: API Key Security

**Problem:** API keys are stored in `os.environ` and written to `active_config.json` (encrypted or plaintext unclear). The `test_runtime_config` endpoint makes a real LLM call with the provided key.

**Files:**
- `app/runtime/active_config.py` — config persistence
- `app/api/routes.py::test_runtime_config` — calls `llm.invoke("hi")` with user-provided key

**Why this matters:** API keys in environment variables are visible in `/proc` on Linux. The test endpoint makes a real call which could be abused.

**Impact:** Medium — security concern for shared environments.

**Suggestion:** Document that this is a single-user local tool. Add a note that keys should not be committed. Consider keyring integration for non-dev use.

**Priority:** P2 | Cost: Low | Risk: Low

### 5.8 Frontend State Management Complexity

**Problem:** `useAgentStore` holds events, artifacts, citations, turns, activeTurnId, status, error — all in one flat store. The `prepareRun` → `startRun` → `appendEvent` → `finishRun` lifecycle is spread across the store.

**Files:**
- `frontend/src/features/agent/store.ts` — 227 lines, single store

**Why this matters:** Flat stores become hard to reason about as features grow. The store already mixes UI state (status, activeTurnId) with domain data (artifacts, citations).

**Impact:** Low (current scale) / Medium (if features grow)

**Suggestion:** Extract `ConversationTurn[]` into a separate store. Keep UI state (status, error) separate from domain data (artifacts, citations).

**Priority:** P2 | Cost: Low | Risk: Low

### 5.9 Chat Service: Complex Heuristic Routing

**Problem:** `ChatService.chat()` has 900+ lines with many heuristic methods: `_has_local_docs_intent`, `_has_cross_source_intent`, `_has_structured_reference_intent`, `_has_section_query_intent`, `_rerank_direct_chat_evidence`, `_apply_source_consistency_cap`, etc.

**Files:**
- `app/services/chat_service.py` — 914 lines

**Why this matters:** Many regex-based intent heuristics are fragile and hard to test exhaustively. The `_directness_score` method has hardcoded domain-specific cue words.

**Impact:** Medium — affects maintainability and predictability.

**Suggestion:** Extract intent detection into a separate `ChatIntentDetector` class. Document the heuristic rationale.

**Priority:** P2 | Cost: Medium | Risk: Low

### 5.10 Incremental Ingest: Hash Store as JSON File

**Problem:** `HashStore` persists content hashes as a JSON file (`data/index/file_hashes.json`). This is a single-writer, non-concurrent store.

**Files:**
- `app/rag/incremental.py::HashStore` — JSON file persistence

**Why this matters:** For a single-user local tool, this is fine. But if multiple processes write (e.g., watcher + API), there's a race condition.

**Impact:** Low (single-user scope)

**Suggestion:** Document that only one process should write to the hash store at a time.

**Priority:** P2 | Cost: Low | Risk: Low

---

## 6. Technical Debt Inventory

| Debt Item | Location | Severity | Notes |
|-----------|----------|----------|-------|
| Heuristic reranker | `app/rag/postprocess.py` | Medium | No semantic reranking |
| Trim-only compressor | `app/rag/postprocess.py` | Low | Acceptable for v0.1 |
| BM25 index not persistent | `app/rag/hybrid_retrieval.py` | Medium | Rebuilt on every restart |
| No eval pipeline runner | `app/evaluation/` | High | Scaffolding exists but unused |
| Hardcoded domain cues in chat | `app/services/chat_service.py` | Medium | Fragile heuristics |
| `Adapters/` directory empty | `adapters/` | Low | Hexagonal arch placeholder |
| `core/` directory empty | `core/` | Low | Hexagonal arch placeholder |
| `tools/` directory | `tools/` | Low | Contains local ASR server |
| `start.bat` only (no cross-platform) | `start.bat` | Low | Windows-only startup script |
| No `.env.example` | root | Medium | Config template missing |

---

## 7. RAG Quality and Evaluation Gaps

### 7.1 What Exists

- `eval/benchmark/sample_eval_set.jsonl` — sample evaluation dataset
- `eval/eval_cases_v3.json` — evaluation cases
- `eval/chunking_eval_report_v4.md`, `v5.md` — manual chunking evaluation reports
- `app/evaluation/` — datasets, metrics, runner, reporting modules (scaffolding)

### 7.2 What's Missing

- **No automated eval runner** — `app/evaluation/runner.py` exists but no CLI or CI integration
- **No citation accuracy metric** — no way to measure if citations actually support answers
- **No recall metric** — no way to measure if relevant chunks are retrieved
- **No insufficient-evidence accuracy metric** — no way to measure refusal precision/recall
- **No regression test suite** — no way to detect quality degradation across commits

### 7.3 Recommendation

Create a minimal evaluation pipeline:

```bash
python -m app.evaluation.runner --dataset eval/benchmark/sample_eval_set.jsonl --output eval/report.json
```

Metrics to track:
- **Retrieval Recall@K** — are relevant chunks in top-K?
- **Citation Precision** — do cited snippets support the answer?
- **Insufficient Evidence Accuracy** — does the system correctly refuse when evidence is lacking?
- **Answer Faithfulness** — does the answer only claim what's in the evidence?

**Priority:** P0 | Cost: Medium | Risk: Low

---

## 8. Product and UX Gaps

### 8.1 Task Mode Switching

The frontend supports `auto | chat | summarize | compare` task types via `useAgentStore.setTaskType()`. The `auto` mode uses `IntentClassifier` to infer intent.

**Gap:** No clear UI indicator of which mode is active or what the classifier decided.

- Evidence: `frontend/src/features/agent/store.ts:taskType`

### 8.2 Citation Display

`citation-list.tsx` renders citations. The backend returns `CitationItem` with `snippet`, `page`, `section`, `citation_label`, `evidence_preview`.

**Gap:** No deep-link from citation back to source document chunk viewer.

- Evidence: `frontend/src/features/agent/components/citation-list.tsx`

### 8.3 Empty/Loading/Error States

**Gap:** The agent panel handles `idle`, `running`, `completed`, `failed`, `cancelled` states but the empty state (no conversations yet) could be more inviting.

- Evidence: `frontend/src/features/agent/store.ts:status`

### 8.4 Settings Page

The settings page covers runtime config, media transcript config, and skill catalog.

**Gap:** No "about" section explaining what MindDock is and its evidence-first philosophy.

- Evidence: `frontend/src/features/settings/settings-view.tsx`

---

## 9. Testing and Maintainability Gaps

### 9.1 Test Coverage

**Well-tested modules:**
- Chat service (`test_chat_service.py`)
- Compare service (`test_compare_service.py`)
- Summarize service (`test_summarize_service.py`)
- Citation building (`test_citation.py`)
- Hybrid retrieval (`test_hybrid_retrieval.py`)
- Incremental ingest (`test_incremental_ingest.py`)
- Watcher (`test_watcher.py`)
- Skill registry (`test_skill_registry.py`)
- Runtime adapter (`test_runtime_adapter.py`)
- Workflow trace (`test_workflow_trace.py`)

**Under-tested modules:**
- `app/rag/postprocess.py` — reranker/compressor heuristic quality
- `app/application/orchestrators.py` — end-to-end orchestration paths
- `app/runtime/resolver.py` — profile scoring edge cases
- Frontend — no frontend test files found

### 9.2 Missing Test Types

- **No integration tests for the full RAG pipeline** (ingest → retrieve → generate → cite)
- **No snapshot/golden tests** for prompt templates
- **No load/performance tests**
- **No frontend component tests**

### 9.3 CI/CD

- Evidence: `.github/` directory exists — likely GitHub Actions but content not verified
- No `Makefile` or `justfile` found
- `pyproject.toml` exists but no test runner configuration verified

---

## 10. What Not to Do

### 10.1 Don't Build a General Agent Platform

MindDock's value is **evidence-cited, verifiable answers from local knowledge**. Adding agent loops, tool calling chains, or multi-agent orchestration would dilute this focus and introduce unverifiable answer paths.

### 10.2 Don't Build an Open Plugin Market

The `SourceSkillSummaryResponse` already has fields like `installable`, `remote_install_supported`, `arbitrary_code_execution` — these signal marketplace intent. Remove them or clearly document that MindDock uses **trusted built-in handlers only**.

### 10.3 Don't Add Heavy Dependencies for Show

Resist adding LangGraph, CrewAI, AutoGen, or similar frameworks. The current architecture is clean and understandable. Heavy frameworks add opacity without proportional value for a personal knowledge tool.

### 10.4 Don't Claim RAG Improvements Without Evaluation

Without a running evaluation pipeline, any claim about "improved retrieval" or "better citations" is unsubstantiated. Build the eval pipeline first, then measure improvements.

### 10.5 Don't Mock Capabilities as Real

The system has `MockLLM`, `mock` media transcript provider, and heuristic reranker. These should be clearly labeled as development/testing aids, not production capabilities. The `mock_used` flag in responses is good — keep it.

### 10.6 Don't Sacrifice Citation Explainability for UI Polish

The citation system is well-designed (`CitationRecord`, `EvidenceObject`, `citation_label`, `evidence_preview`). Don't hide this behind a simplified "sources" display that loses the evidence chain.

### 10.7 Don't Stack Agent Workflows Without Citation Verification

Adding complex agent workflows (plan → execute → reflect → retry) before verifying citation correctness would create a system that confidently produces wrong citations at scale.

---

## 11. Prioritized Roadmap

### Phase 1: 1 Week — Cleanup & Documentation

| Task | Priority | Cost | Risk |
|------|----------|------|------|
| Create `.env.example` with all config fields | P0 | Low | Low |
| Add `Makefile` with `install`, `test`, `eval`, `start` targets | P0 | Low | Low |
| Fix `start.bat` to handle missing dependencies gracefully | P1 | Low | Low |
| Add `CONTRIBUTING.md` section on architecture overview | P1 | Low | Low |
| Document that `adapters/` and `core/` are hexagonal arch placeholders | P2 | Low | Low |
| Add `docs/architecture.md` with the map from this audit | P1 | Low | Low |
| Remove or clearly label marketplace-sounding fields in Source Skill API | P2 | Low | Low |

### Phase 2: 1 Month — Quality & Stability

| Task | Priority | Cost | Risk |
|------|----------|------|------|
| Wire up `app/evaluation/runner.py` as CLI entry point | P0 | Low | Low |
| Create minimal eval dataset (20-30 Q&A pairs with expected citations) | P0 | Medium | Low |
| Enable hybrid retrieval by default | P1 | Low | Low |
| Add citation verification step (entailment check) | P1 | High | Medium |
| Extract `ChatIntentDetector` from `ChatService` | P2 | Medium | Low |
| Add frontend component tests (Vitest) | P2 | Medium | Low |
| Persist BM25 index to disk | P1 | Medium | Low |
| Add `cross_encoder` rerank provider option | P1 | Medium | Low |

### Phase 3: Long-term — Research & Open Source

| Task | Priority | Cost | Risk |
|------|----------|------|------|
| Evidence-first RAG evaluation benchmark | Research | High | Low |
| Citation correctness benchmark (NLI-based) | Research | High | Medium |
| Personal knowledge base incremental indexing optimization | Engineering | Medium | Low |
| Multi-source grounding with conflict detection | Research | High | Medium |
| Workflow trace observability dashboard | Engineering | Medium | Low |
| Local-first privacy-preserving RAG whitepaper | Research | Low | Low |

---

## 12. Suggested Next Prompts for Implementation

### "Wire up the evaluation pipeline"

Create a CLI entry point for `app/evaluation/runner.py` that reads `eval/benchmark/sample_eval_set.jsonl`, runs the RAG pipeline on each query, and outputs a JSON report with retrieval recall, citation precision, and insufficient-evidence accuracy.

### "Enable hybrid retrieval by default and persist BM25 index"

Change `hybrid_retrieval_enabled` default to `True`. Add a `BM25Index.persist(path)` method that saves the index to disk, and `BM25Index.load(path)` that restores it. Invalidate on ingest.

### "Add a cross-encoder rerank provider"

Create a `CrossEncoderReranker` class in `app/rag/postprocess.py` that uses `sentence-transformers` CrossEncoder. Add `rerank_provider="cross_encoder"` config option. Keep `heuristic` as fallback.

### "Extract ChatIntentDetector from ChatService"

Move `_has_local_docs_intent`, `_has_cross_source_intent`, `_has_structured_reference_intent`, `_has_section_query_intent`, `_directness_score`, `_answer_cue_score` into a `ChatIntentDetector` class. Make it injectable into `ChatService`.

### "Create architecture documentation"

Write `docs/architecture.md` based on Section 3 of this audit. Include the execution path diagram, module responsibilities, and data flow.

### "Add citation verification step"

After `build_citation()` and `build_evidence()`, add a `verify_citation(answer_claim, cited_snippet)` function that checks if the claim is entailed by the snippet. Use a lightweight NLI model or LLM call.

---

*End of audit report.*
