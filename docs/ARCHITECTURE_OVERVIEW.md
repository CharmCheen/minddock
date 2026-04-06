# Architecture Overview

## Positioning

This document describes the implemented backend architecture after the application/runtime/skill extensibility pass.

The project now has two formalized halves:

- source/ingest domain
- retrieval/citation/filter domain

On top of those, the program now also has:

- a frontend-facing application/orchestrator layer
- a runtime port/adapter layer
- a minimal skill-registry extension surface

The intent is to keep the core program maintainable without turning it into an over-abstracted framework.

## Layered Structure

### API Layer

Files:

- `app/main.py`
- `app/api/routes.py`
- `app/api/schemas.py`
- `app/core/exceptions.py`
- `app/api/presenters.py`

Responsibilities:

- expose HTTP endpoints
- validate request payloads
- call the application facade instead of wiring many low-level services directly
- convert internal result objects to API schemas through a dedicated presenter layer
- keep error semantics uniform

### Application Layer

Files:

- `app/application/orchestrators.py`
- `app/application/assembly.py`

Responsibilities:

- provide a stable higher-level entrypoint for frontend, desktop, or CLI consumers
- compose services without duplicating their business logic
- gather system extension registries in one lightweight assembly module

Current facade/orchestrator objects:

- `FrontendFacade`
- `ChatOrchestrator`
- `KnowledgeBaseOrchestrator`
- `SkillOrchestrator`

### Service Layer

Files:

- `app/services/ingest_service.py`
- `app/services/search_service.py`
- `app/services/chat_service.py`
- `app/services/summarize_service.py`
- `app/services/grounded_generation.py`

Responsibilities:

- `ingest_service`: source-oriented batch ingest
- `search_service`: retrieval entrypoint returning `SearchServiceResult`
- `chat_service`: retrieval -> selection -> rerank/compress -> context -> generation -> `ChatServiceResult`
- `summarize_service`: retrieval workflow -> rerank/compress -> summary chain -> optional Mermaid output -> `SummarizeServiceResult`
- `grounded_generation`: citation/context conversion helpers

The service layer remains the main use-case implementation layer. The application layer sits above it and is intended to become the preferred entrypoint for frontend-style consumers.

### Source Processing Layer

Files:

- `app/rag/source_models.py`
- `app/rag/source_loader.py`
- `app/rag/ingest.py`
- `app/rag/url_loader.py`
- `app/rag/incremental.py`
- `app/rag/watcher.py`

Responsibilities:

- define source/ingest domain objects
- resolve loaders by source type
- build normalized `DocumentPayload`
- preserve source identity and metadata consistency

### Retrieval Layer

Files:

- `app/rag/retrieval_models.py`
- `app/rag/postprocess.py`
- `app/rag/vectorstore.py`
- `app/workflows/langgraph_pipeline.py`

Responsibilities:

- define retrieval/citation/context/filter domain objects
- map vector-store results into `RetrievedChunk`
- apply controlled filter semantics
- rerank and compress without breaking citation traceability

### Runtime Layer

Files:

- `app/runtime/base.py`
- `app/runtime/models.py`
- `app/runtime/adapters.py`
- `app/runtime/registry.py`
- `app/llm/factory.py`
- `app/llm/openai_compatible.py`
- `app/llm/mock.py`

Responsibilities:

- define the formal runtime port: `GenerationRuntime`
- normalize runtime input/output through `RuntimeRequest` / `RuntimeResponse`
- host the current LangChain-backed adapter in a registry-friendly form
- keep no-key and provider-failure fallback behavior available

Important positioning:

- LangChain remains the current primary implementation
- LangChain is no longer the only architectural center
- future AutoGen/multi-LLM/local runtime work should plug in as additional adapters

### Skill Layer

Files:

- `app/skills/models.py`
- `app/skills/registry.py`

Responsibilities:

- define the formal skill port and execution context
- register stable skill descriptors
- provide a controlled execution boundary for future tool/skill systems

Current status:

- this is a skeleton, not a rich skill platform
- one minimal example skill (`echo`) is registered to validate the path

## Formal Retrieval Model

Core objects:

- `RetrievalFilters`
- `RetrievedChunk`
- `CitationRecord`
- `ContextBlock`
- `SearchHitRecord`
- `SearchResult`
- `GroundedSelectionResult`

### Response / contract side

Core objects:

- `SearchResponse`
- `ChatResponse`
- `SummarizeResponse`
- `IngestResponse`
- `CitationItem`
- `FailedSourceItem`
- `ErrorResponse`

### Service / application side

Core objects:

- `UseCaseMetadata`
- `SearchServiceResult`
- `ChatServiceResult`
- `SummarizeServiceResult`
- `IngestServiceResult`
- `RetrievalPreparationResult`
- `DocumentEvidenceGroup`

Important rule:

- internal services and postprocess code should operate on these objects
- API boundaries should serialize them through response schemas and presenters instead of endpoint-local dict assembly

## Shared Retrieval Flow

Current shared chain:

```text
query + RetrievalFilters
  -> vectorstore.search_by_text()
  -> RetrievedChunk list
  -> grounded selection
  -> rerank
  -> compress
  -> ContextBlock
  -> citations / generation / summarize
```

This same chain underlies:

- `/search`
- `/chat`
- `/summarize`

At the API edge that chain becomes:

```text
formal service result
  -> application/orchestrator facade
  -> app/api/presenters.py
  -> Pydantic response model
  -> JSON response body
```

The intended reuse order is now:

1. frontend/desktop clients: application facade
2. internal tools that need use-case detail: service results
3. HTTP consumers: API schemas/presenters

## Citation and Compression Relationship

`RetrievedChunk` now keeps the relationship between:

- `text`
- `compressed_text`
- `original_text`

Rules:

- prompt context uses compressed text when available
- citation snippets use original text when available
- rerank/compress can add metadata such as `rerank_score`, `retrieval_rank`, `compression_applied`
- chunk identity fields must not change during post-processing

## Filter Design

The filter system is intentionally controlled.

Supported capabilities:

- exact `section`
- single or multi-value `source`
- single or multi-value `source_type`
- `title_contains`
- `requested_url_contains`
- `page_from` / `page_to`

Execution split:

- vector store handles exact-match-friendly constraints where possible
- retrieval layer applies post-filtering for multi-value and contains/range conditions

This avoids building a complex DSL while still covering useful real cases.

## Source and Retrieval Boundary

Source layer owns:

- source identity
- source loading
- chunk creation

Retrieval layer owns:

- vector-store search
- retrieval-hit normalization
- citation/context/postprocess semantics

API layer owns:

- request validation
- response schema construction
- error serialization
- preserving backward-compatible contract shapes while adding controlled fields

Service layer owns:

- use-case orchestration
- service-level metadata such as `retrieved_count`, `mode`, `output_format`, `partial_failure`
- insufficient-evidence and partial-failure semantics

Workflow layer owns:

- graph/state progression for retrieval preparation
- grouped evidence construction for downstream use cases

That separation is intentional so new source types do not force retrieval logic changes, and new retrieval logic does not force source-loading rewrites.

## Known Engineering Limits

- URL extraction remains minimal HTML body parsing
- enhanced filters are still intentionally limited
- post-filtering may fetch extra vector-store candidates
- Chroma rebuild behavior on Windows is mitigated, not guaranteed
- the skill layer is only a minimal registry skeleton in this stage
- the runtime registry currently has one primary registered adapter (`langchain`)
