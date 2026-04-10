# API Contracts — Personal Knowledge Management Assistant

> **Generated from**: `app/api/routes.py`, `app/api/schemas.py`, `app/application/models.py`, `app/application/client_events.py`, `app/application/artifacts.py`, `app/rag/retrieval_models.py`, `app/rag/source_models.py`, `app/application/events.py`, `app/application/run_control.py`, `app/skills/models.py`
> **Purpose**: Authoritative TypeScript/FastAPI contract reference for frontend–backend integration.

---

## Table of Contents

1. [Core API Endpoints](#1-core-api-endpoints)
2. [TypeScript Type Definitions](#2-typescript-type-definitions)
3. [SSE Streaming Contract](#3-sse-streaming-contract)
4. [Document Ingest Status](#4-document-ingest-status)
5. [Architecture Recommendations](#5-architecture-recommendations)

---

## 1. Core API Endpoints

| Method | Path | Summary | Response Schema |
|--------|------|---------|-----------------|
| `GET` | `/` | Service info | `object { service, version }` |
| `GET` | `/health` | Health check | `object { status, service, version }` |
| `POST` | `/ingest` | Ingest KB documents | `IngestResponse` |
| `GET` | `/sources` | List indexed sources | `SourceCatalogResponse` |
| `GET` | `/sources/by-source` | Get source detail by source string | `SourceDetailResponse` |
| `GET` | `/sources/by-source/chunks` | Inspect source chunks | `SourceChunkPageResponse` |
| `DELETE` | `/sources/by-source` | Delete source by source string | `DeleteSourceResponse` |
| `POST` | `/sources/by-source/reingest` | Reingest by source string | `ReingestSourceResponse` |
| `GET` | `/sources/{doc_id}` | Get source detail by doc_id | `SourceDetailResponse` |
| `GET` | `/sources/{doc_id}/chunks` | Inspect chunks by doc_id | `SourceChunkPageResponse` |
| `DELETE` | `/sources/{doc_id}` | Delete source by doc_id | `DeleteSourceResponse` |
| `POST` | `/sources/{doc_id}/reingest` | Reingest by doc_id | `ReingestSourceResponse` |
| `POST` | `/search` | Semantic search with citations | `SearchResponse` |
| `POST` | `/chat` | Grounded chat with citations | `ChatResponse` |
| `POST` | `/summarize` | Grounded summarization | `SummarizeResponse` |
| `POST` | `/compare` | Grounded document compare | `CompareResponse` |
| `POST` | `/frontend/execute` | Unified execution (non-streaming) | `UnifiedExecutionResponseBody` |
| `POST` | `/frontend/execute/stream` | **SSE stream** for unified execution | `text/event-stream` |
| `GET` | `/frontend/runtime-profiles` | List selectable runtime profiles | `RuntimeProfileListResponse` |
| `GET` | `/frontend/skills` | List discoverable skills | `SkillListResponse` |
| `GET` | `/frontend/skills/{skill_id}` | Get skill detail | `SkillDetailResponse` |
| `GET` | `/frontend/runs/{run_id}` | Get transient run status | `RunSummaryResponse` |
| `GET` | `/frontend/runs/{run_id}/events` | Replay recent client events | `RunEventListResponse` |
| `POST` | `/frontend/runs/{run_id}/cancel` | Request run cancellation | `CancelRunResponse` |

---

## 2. TypeScript Type Definitions

### 2.1 Enums / String Literals

```typescript
// Task types for unified execution
type TaskType = "chat" | "summarize" | "search" | "compare" | "structured_generation";

// Output rendering modes
type OutputMode = "text" | "mermaid" | "structured";

// Citation policy
type CitationPolicy = "required" | "preferred" | "none";

// Evidence support status (grounded answer confidence)
type SupportStatus = "supported" | "partially_supported" | "insufficient_evidence" | "conflicting_evidence";

// Refusal reasons when generation is declined
type RefusalReason = "no_relevant_evidence" | "insufficient_context" | "conflicting_sources" | "out_of_scope";

// Evidence freshness relative to current source state
type EvidenceFreshness = "fresh" | "stale_possible" | "invalidated";

// Source type filter
type SourceType = "file" | "url";

// Skill invocation mode
type SkillPolicyMode = "disabled" | "manual_only" | "allowlisted" | "planner_allowed" | "runtime_native_allowed";

// Client event channel (for SSE routing)
type ClientEventChannel = "progress" | "artifact" | "diagnostic" | "system";

// Client event visibility
type EventVisibility = "public" | "debug" | "internal";

// Client event kind (SSE `event:` field value)
type ClientEventKind =
  | "run_started"
  | "progress"
  | "artifact"
  | "warning"
  | "heartbeat"
  | "completed"
  | "failed"
  | "info";

// Progress phase inside a run
type ProgressPhase =
  | "preparing"
  | "resolving_runtime"
  | "retrieving"
  | "generating"
  | "formatting"
  | "invoking_skill"
  | "finalizing";

// Artifact kind (BaseArtifact.kind)
type ArtifactKind = "text" | "mermaid" | "search_results" | "structured_json" | "skill_result" | "warning";

// Run lifecycle status
type ExecutionRunStatus =
  | "pending"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed"
  | "expired";

// Summarization mode
type SummarizeMode = "basic" | "map_reduce";

// Output format for summarize
type SummarizeOutputFormat = "text" | "mermaid";
```

---

### 2.2 Citation & Evidence (溯源抽象)

```typescript
/** One traceable citation bound to a retrieved chunk. */
interface CitationItem {
  doc_id: string;
  chunk_id: string;
  source: string;
  snippet: string;
  page: number | null;
  anchor: string | null;
  title: string | null;
  section: string | null;
  location: string | null;
  ref: string | null;
}

/**
 * Stable machine-consumable evidence object derived from one retrieved chunk.
 * Used inside GroundedAnswer and ComparedPoint.
 */
interface EvidenceItem {
  doc_id: string;
  chunk_id: string;
  source: string;
  snippet: string;
  page: number | null;
  anchor: string | null;
  score: number | null;
  source_version: string | null;
  content_hash: string | null;
  freshness: EvidenceFreshness;
}

/**
 * Grounded answer or summary with explicit support semantics.
 * Returned inside ChatResponse, SummarizeResponse, and Artifacts.
 */
interface GroundedAnswerItem {
  answer: string;
  evidence: EvidenceItem[];
  support_status: SupportStatus;
  refusal_reason: RefusalReason | null;
}

/**
 * One grounded compare statement with paired evidence from each side.
 * Used inside CompareResultItem.
 */
interface ComparedPointItem {
  statement: string;
  left_evidence: EvidenceItem[];
  right_evidence: EvidenceItem[];
  summary_note: string | null;
}

/**
 * Full grounded compare payload for the compare endpoint.
 */
interface CompareResultItem {
  query: string;
  common_points: ComparedPointItem[];
  differences: ComparedPointItem[];
  conflicts: ComparedPointItem[];
  support_status: SupportStatus;
  refusal_reason: RefusalReason | null;
}
```

---

### 2.3 Streaming / Client Events (流式通信抽象)

```typescript
/**
 * Base client-facing event envelope for SSE.
 * The SSE `event:` field is set to `kind.value`; `data` is the JSON-serialized payload.
 */
interface ClientEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  kind: ClientEventKind;           // maps to SSE "event:" field
  channel: ClientEventChannel;
  visibility: EventVisibility;
  timestamp: string;               // ISO-8601
  cursor: string;                  // format: "{run_id}:{sequence}"
  payload: ClientEventPayload;     // discriminant union — see below
}

/** Union of all possible client event payloads */
type ClientEventPayload =
  | ClientRunStartedPayload
  | ClientProgressPayload
  | ClientArtifactPayload
  | ClientWarningPayload
  | ClientHeartbeatPayload
  | ClientCompletedPayload
  | ClientFailedPayload;

interface ClientRunStartedPayload {
  task_type: TaskType;
  output_mode: OutputMode;
}

interface ClientProgressPayload {
  phase: ProgressPhase;
  status: string;          // e.g. "started" | "completed"
  message: string | null;
}

interface ClientArtifactPayload {
  artifact_index: number;
  artifact: BaseArtifact;  // See §2.4
}

interface ClientWarningPayload {
  message: string;
}

interface ClientHeartbeatPayload {
  message: string;         // default: "keepalive"
}

interface ClientCompletedPayload {
  artifact_count: number;
  primary_artifact_kind: ArtifactKind | null;
  partial_failure: boolean;
}

interface ClientFailedPayload {
  error: string;
  detail: string;
}
```

---

### 2.4 Artifacts (统一输出抽象)

```typescript
/** Base artifact — all artifact types extend this */
interface BaseArtifact {
  artifact_id: string;
  kind: ArtifactKind;
  title: string | null;
  description: string | null;
  render_hint: string | null;   // e.g. "markdown", "json", "mermaid", "list"
  source_step_id: string | null;
  metadata: Record<string, unknown>;
}

/** Plain text artifact */
interface TextArtifact extends BaseArtifact {
  kind: "text";
  text: string;
}

/** Mermaid diagram artifact */
interface MermaidArtifact extends BaseArtifact {
  kind: "mermaid";
  mermaid_code: string;
}

/** Search results list artifact */
interface SearchResultsArtifact extends BaseArtifact {
  kind: "search_results";
  items: SearchResultItemArtifact[];
  total: number;
  offset: number;
  limit: number;
}

interface SearchResultItemArtifact {
  chunk_id: string;
  doc_id: string;
  source: string;
  source_type: string;
  title: string | null;
  snippet: string;
  score: number | null;
  page: number | null;
  anchor: string | null;
}

/** Structured JSON artifact */
interface StructuredJsonArtifact extends BaseArtifact {
  kind: "structured_json";
  data: Record<string, unknown>;
  schema_name: string | null;       // e.g. "compare.v1", "summary.v1"
  validation_notes: string[];
}

/** Skill execution result artifact */
interface SkillResultArtifact extends BaseArtifact {
  kind: "skill_result";
  skill_name: string;
  payload: Record<string, unknown>;
  summary_text: string | null;
}

/**
 * Serializable artifact returned by UnifiedExecutionResponseBody.
 * Equivalent to the union of all artifact types above.
 */
interface ArtifactResponseItem {
  artifact_id: string;
  kind: string;
  title: string | null;
  description: string | null;
  render_hint: string | null;
  source_step_id: string | null;
  content: Record<string, unknown>;   // varies by kind — see below
  metadata: Record<string, unknown>;
}

/*
 * Artifact content shapes by kind:
 * kind="text"           → content: { text: string }
 * kind="mermaid"        → content: { mermaid_code: string }
 * kind="search_results" → content: { items: SearchResultItemArtifact[], total, offset, limit }
 * kind="structured_json"→ content: { data, schema_name, validation_notes }
 * kind="skill_result"   → content: { skill_name, payload, summary_text }
 */
```

---

### 2.5 Source / Document Management (文档管理抽象)

```typescript
/** Current source lifecycle state — stored as a plain string for ingest_status */
interface SourceStateItem {
  doc_id: string;
  source: string;
  current_version: string | null;
  content_hash: string | null;
  last_ingested_at: string | null;   // ISO-8601
  chunk_count: number;
  ingest_status: string | null;      // NOTE: no formal enum; value is "ready" in practice
}

/** One indexed source in the catalog */
interface SourceCatalogItem {
  doc_id: string;
  source: string;
  source_type: string;       // "file" | "url"
  title: string;
  chunk_count: number;
  sections: string[];
  pages: number[];
  requested_url: string | null;
  final_url: string | null;
  source_state: SourceStateItem | null;
}

/** Paginated chunk preview for one source */
interface SourceChunkPreviewItem {
  chunk_id: string;
  chunk_index: number | null;
  preview_text: string;
  title: string;
  section: string | null;
  location: string | null;
  ref: string | null;
  page: number | null;
  anchor: string | null;
  admin_metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Request/Response shapes
// ---------------------------------------------------------------------------

interface SourceCatalogResponse {
  items: SourceCatalogItem[];
  total: number;
}

interface SourceDetailResponse {
  found: boolean;
  item: SourceCatalogItem | null;
  representative_metadata: Record<string, unknown>;
  admin_metadata: Record<string, unknown>;
}

interface SourceChunkPageResponse {
  found: boolean;
  item: SourceCatalogItem | null;
  total_chunks: number;
  returned_chunks: number;
  limit: number;
  offset: number;
  chunks: SourceChunkPreviewItem[];
  representative_metadata: Record<string, unknown>;
  admin_metadata: Record<string, unknown>;
}

interface DeleteSourceResponse {
  found: boolean;
  doc_id: string | null;
  source: string | null;
  source_type: string | null;
  deleted_chunks: number;
}

interface ReingestSourceResponse {
  found: boolean;
  ok: boolean;
  doc_id: string | null;
  source: string | null;
  source_type: string | null;
  chunks_upserted: number;
  chunks_deleted: number;
  failure: FailedSourceItem | null;
}

interface FailedSourceItem {
  source: string;
  source_type: string;
  reason: string;
}

interface IngestResponse {
  documents: number;
  chunks: number;
  ingested_sources: string[];
  failed_sources: FailedSourceItem[];
  partial_failure: boolean;
}
```

---

### 2.6 Retrieval & Query

```typescript
/** Shared metadata filter for search/chat/summarize/compare */
interface MetadataFilters {
  source?: string | string[];
  section?: string | null;
  source_type?: SourceType | SourceType[] | null;
  title_contains?: string | null;
  requested_url_contains?: string | null;
  page_from?: number | null;
  page_to?: number | null;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

interface SearchRequest {
  query: string;
  top_k?: number;          // default 5, range 1–20
  filters?: MetadataFilters | null;
}

interface SearchHit {
  text: string;
  doc_id: string;
  chunk_id: string;
  source: string;
  source_type: string;
  title: string | null;
  section: string | null;
  distance: number | null;
  citation: CitationItem;
}

interface SearchResponse {
  query: string;
  top_k: number;
  hits: SearchHit[];
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

interface ChatRequest {
  query: string;
  top_k?: number;           // default 3, range 1–10
  filters?: MetadataFilters | null;
}

interface ChatResponse {
  answer: string;
  evidence: EvidenceItem[];
  support_status: SupportStatus;
  refusal_reason: RefusalReason | null;
  citations: CitationItem[];
  retrieved_count: number;
  mode: string;             // e.g. "grounded"
}

// ---------------------------------------------------------------------------
// Summarize
// ---------------------------------------------------------------------------

interface SummarizeRequest {
  query?: string | null;
  topic?: string | null;
  top_k?: number;           // default 5, range 1–20
  filters?: MetadataFilters | null;
  mode?: SummarizeMode;     // "basic" | "map_reduce"
  output_format?: SummarizeOutputFormat; // "text" | "mermaid"
}

interface SummarizeResponse {
  summary: string;
  evidence: EvidenceItem[];
  support_status: SupportStatus;
  refusal_reason: RefusalReason | null;
  citations: CitationItem[];
  retrieved_count: number;
  mode: SummarizeMode;
  output_format: SummarizeOutputFormat;
  structured_output: string | null;   // mermaid code when output_format="mermaid"
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

interface CompareRequest {
  question: string;
  top_k?: number;           // default 6, range 2–20
  filters?: MetadataFilters | null;
}

interface CompareResponse {
  query: string;
  common_points: ComparedPointItem[];
  differences: ComparedPointItem[];
  conflicts: ComparedPointItem[];
  support_status: SupportStatus;
  refusal_reason: RefusalReason | null;
  citations: CitationItem[];
  retrieved_count: number;
  mode: string;             // e.g. "grounded_compare"
}
```

---

### 2.7 Unified Execution (前端统一执行)

```typescript
// ---------------------------------------------------------------------------
// Request
// ---------------------------------------------------------------------------

interface SkillPolicyItem {
  mode: SkillPolicyMode;
  allowlist: string[];
  denied_skill_ids: string[];
  require_public_listing: boolean;
  allow_external_io: boolean;
}

interface ExecutionPolicyItem {
  preferred_profile_id: string | null;
  allowed_profile_ids: string[];
  selection_mode: "auto" | "preferred" | "strict";
  optimization_target: "latency" | "quality" | "cost" | "privacy";
  locality_preference: "local_only" | "cloud_allowed" | "cloud_preferred";
  require_skill_support: boolean;
  require_structured_output: boolean;
  require_citations: boolean;
}

interface UnifiedExecutionRequestBody {
  task_type: TaskType;
  user_input: string;
  top_k?: number;           // default 5, range 1–20
  filters?: MetadataFilters | null;
  execution_policy?: ExecutionPolicyItem | null;
  output_mode?: OutputMode;
  citation_policy?: CitationPolicy;
  skill_policy?: SkillPolicyItem;
  requested_skill_id?: string | null;
  requested_skill_arguments?: Record<string, unknown>;
  conversation_metadata?: Record<string, unknown>;
  task_options?: Record<string, unknown>;
  debug?: boolean;
  include_metadata?: boolean;   // default true
  include_events?: boolean;      // default false
}

// ---------------------------------------------------------------------------
// Response
// ---------------------------------------------------------------------------

interface SkillInvocationItem {
  name: string;
  ok: boolean;
  message: string | null;
  output_preview: string | null;
}

interface ServiceIssueItem {
  code: string;
  message: string;
  severity: string;         // e.g. "warning"
  source: string | null;
}

interface RetrievalStatsItem {
  retrieved_hits: number;
  grounded_hits: number;
  reranked_hits: number;
  returned_hits: number;
}

interface UnifiedExecutionMetadataResponse {
  selected_runtime: string | null;
  selected_profile_id: string | null;
  selected_provider_kind: string | null;
  selected_model_name: string | null;
  runtime_capabilities_matched: string[];
  resolved_capabilities: string[];
  execution_steps_executed: string[];
  artifact_kinds_returned: string[];
  primary_artifact_kind: ArtifactKind | null;
  artifact_count: number;
  search_result_count: number;
  skill_artifact_count: number;
  skill_invocations: SkillInvocationItem[];
  warnings: string[];
  issues: ServiceIssueItem[];
  insufficient_evidence: boolean;
  support_status: SupportStatus | null;
  refusal_reason: RefusalReason | null;
  partial_failure: boolean;
  fallback_used: boolean;
  selection_reason: string | null;
  policy_applied: string | null;
  filter_applied: boolean;
  retrieval_stats: RetrievalStatsItem | null;
}

interface ExecutionSummaryResponse {
  selected_runtime: string | null;
  selected_profile_id: string | null;
  selected_provider_kind: string | null;
  selected_model_name: string | null;
  selected_capabilities: string[];
  fallback_used: boolean;
  selection_reason: string | null;
  policy_applied: string | null;
  execution_steps_executed: string[];
  artifact_kinds_returned: string[];
  primary_artifact_kind: ArtifactKind | null;
  artifact_count: number;
  search_result_count: number;
  skill_artifact_count: number;
  skill_invocations: SkillInvocationItem[];
  warnings: string[];
  issues: ServiceIssueItem[];
}

interface OutputBlockItem {
  kind: string;
  content: string;
  title: string | null;
  metadata: Record<string, unknown>;
}

interface UnifiedExecutionResponseBody {
  task_type: TaskType;
  run_id: string | null;
  event_count: number;
  artifacts: ArtifactResponseItem[];
  output_blocks: OutputBlockItem[];   // deprecated compat projection
  events: ExecutionEventResponseItem[] | null;  // only when include_events=true
  citations: CitationItem[];
  grounded_answer: GroundedAnswerItem | null;
  compare_result: CompareResultItem | null;
  metadata: UnifiedExecutionMetadataResponse;
  execution_summary: ExecutionSummaryResponse;
}
```

---

### 2.8 Run Management / Long-Running Tasks (长耗时任务抽象)

```typescript
// ---------------------------------------------------------------------------
// Run Status
// ---------------------------------------------------------------------------

interface RunSummaryResponse {
  run_id: string;
  status: ExecutionRunStatus;
  created_at: string;       // ISO-8601
  updated_at: string;       // ISO-8601
  selected_runtime: string | null;
  selected_profile_id: string | null;
  selected_provider_kind: string | null;
  event_count: number;
  cancellation_requested: boolean;
  has_final_response: boolean;
  final_response: {
    task_type: TaskType;
    artifact_count: number;
    primary_artifact_kind: ArtifactKind | null;
  } | null;
  error: { error: string; detail: string } | null;
}

interface RunEventListResponse {
  run_id: string;
  status: ExecutionRunStatus;
  event_count: number;
  items: ClientEventResponseItem[];
}

interface CancelRunResponse {
  run_id: string;
  status: ExecutionRunStatus;
  cancellation_requested: boolean;
  accepted: boolean;        // false if run already terminal
  detail: string;           // human-readable message
}

// ---------------------------------------------------------------------------
// SSE event replay (internal event shapes)
// ---------------------------------------------------------------------------

interface ExecutionEventResponseItem {
  event_id: string;
  run_id: string;
  sequence: number;
  kind: string;             // ExecutionEventKind value
  step_id: string | null;
  timestamp: string;
  payload: Record<string, unknown>;
  metadata_delta: ExecutionMetadataDeltaResponse | null;
  visibility: string;
  debug_level: string;
}

interface ExecutionMetadataDeltaResponse {
  selected_runtime: string | null;
  selected_profile_id: string | null;
  selected_provider_kind: string | null;
  selected_model_name: string | null;
  execution_steps_executed: string[];
  artifact_kinds_returned: string[];
  artifact_count: number;
  partial_failure: boolean | null;
  warnings: string[];
  issues: ServiceIssueItem[];
}
```

---

### 2.9 Skills Catalog

```typescript
interface SkillListResponse {
  skills: SkillCatalogEntry[];
}

interface SkillCatalogEntry {
  skill_id: string;
  display_name: string;
  description: string;
  version: string;
  capability_tags: string[];       // SkillCapabilityTag values
  invocation_mode: string;
  enabled: boolean;
  safe_for_public_listing: boolean;
  produces_artifact_kind: ArtifactKind | null;
}

interface SkillDetailResponse {
  skill_id: string;
  display_name: string;
  description: string;
  version: string;
  capability_tags: string[];
  invocation_mode: string;
  enabled: boolean;
  safe_for_public_listing: boolean;
  timeout_hint_ms: number | null;
  produces_artifact_kind: ArtifactKind | null;
  input_schema: SkillSchema | null;
  output_schema: SkillSchema | null;
  visibility_notes: string[];
  safety_notes: string[];
}

interface SkillSchema {
  schema_name: string;
  description: string;
  fields: SkillSchemaField[];
}

interface SkillSchemaField {
  name: string;
  field_type: string;
  description: string;
  required: boolean;
  enum_values: string[];
  items_type: string | null;
  default: unknown;
}
```

---

## 3. SSE Streaming Contract

**Endpoint**: `POST /frontend/execute/stream`
**Media Type**: `text/event-stream`

### Wire Format

Each SSE chunk is emitted as:

```
event: {ClientEventKind}\n
data: {JSON.stringify(ClientEvent)}\n\n
```

### Event Sequence for a Typical Run

| # | SSE `event:` | Trigger | Key Payload Fields |
|---|-------------|---------|-------------------|
| 1 | `run_started` | Run begins | `task_type`, `output_mode` |
| 2 | `progress` | Execution plan built | `phase="preparing"`, `status="completed"` |
| 3 | `progress` | Step starts | `phase`, `status="started"` |
| 4 | `progress` | Step completes | `phase`, `status="completed"` (DEBUG visibility, skipped unless `?debug=true`) |
| 5 | `artifact` | Each artifact emitted | `artifact`, `artifact_index` |
| 6 | `warning` | Non-fatal issue | `message` |
| 7 | `progress` | Runtime resolved | `phase="resolving_runtime"`, `status="completed"` |
| 8 | `completed` | Run finishes OK | `artifact_count`, `primary_artifact_kind`, `partial_failure` |
| — | `failed` | Run throws | `error`, `detail` |
| — | `heartbeat` | Long gap between events | `message="keepalive"` |

> **Heartbeat**: A synthetic `heartbeat` event is injected every N seconds (configured server-side, default 5 s) when there are no real events. Clients should treat it as a keepalive.

### Frontend Consumption Pattern

```typescript
const eventSource = new EventSource(
  `/frontend/execute/stream`,
  { method: 'POST', body: JSON.stringify(requestBody), headers: { 'Content-Type': 'application/json' } }
);

// Note: Standard EventSource does not support POST with body.
// Workaround: use fetch + ReadableStream (Web Streams API) or a wrapper library.
// The SSE data field is a JSON-serialized ClientEvent.

eventSource.addEventListener('run_started', (e) => {
  const payload: ClientRunStartedPayload = JSON.parse(e.data);
});

eventSource.addEventListener('progress', (e) => {
  const payload: ClientProgressPayload = JSON.parse(e.data);
  updateProgressUI(payload.phase, payload.status);
});

eventSource.addEventListener('artifact', (e) => {
  const payload: ClientArtifactPayload = JSON.parse(e.data);
  renderArtifact(payload.artifact);
});

eventSource.addEventListener('completed', (e) => {
  const payload: ClientCompletedPayload = JSON.parse(e.data);
  finishUI(payload.artifact_count);
});

eventSource.addEventListener('failed', (e) => {
  const payload: ClientFailedPayload = JSON.parse(e.data);
  showError(payload.error, payload.detail);
});

eventSource.addEventListener('heartbeat', (e) => {
  // keepalive — reset connection timer
});
```

### Client Event → SSE Channel Mapping

| `ClientEventKind` | Maps to SSE channel (for filtering) |
|-------------------|-------------------------------------|
| `RUN_STARTED` | `system` |
| `PROGRESS` | `progress` |
| `ARTIFACT` | `artifact` |
| `WARNING` | `diagnostic` |
| `HEARTBEAT` | `system` |
| `COMPLETED` | `system` |
| `FAILED` | `system` |
| `INFO` | `system` |

---

## 4. Document Ingest Status

### Current State (Gap: No Formal Enum)

The `ingest_status` field in `SourceStateItem` is a plain `string | null`. The codebase only ever writes the literal value `"ready"` to this field after a successful ingest. There is **no formal state machine** for document lifecycle status.

**Current observed values:**

| Value | Meaning |
|-------|---------|
| `"ready"` | All chunks upserted, document fully indexed |
| `null` | Not yet indexed or state is indeterminate |

### Recommended State Machine (for future implementation)

```
                    ┌─────────────────────────────────────────────┐
                    │                 pending                      │
                    │  (document registered, not yet processed)    │
                    └─────────────────────┬───────────────────────┘
                                          │ ingest started
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │                chunking                     │
                    │  (splitting into semantic chunks in progress)│
                    └─────────────────────┬───────────────────────┘
                                          │ chunks written
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │                 indexing                     │
                    │  (vector embedding + vector store upsert)    │
                    └─────────────────────┬───────────────────────┘
                                          │ all done
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │                 ready                       │
                    │  (fully indexed, searchable)                │
                    └─────────────────────────────────────────────┘
```

---

## 5. Architecture Recommendations

### 5.1 Formalize `IngestStatus` Enum

**Severity**: Medium
**File**: `app/rag/source_models.py`

`SourceState.ingest_status` is a free-form string. A `StrEnum` should replace it to enable:
- Frontend progress UI with accurate state labels
- Exhaustive switch-case checking in both backend and frontend

```python
class IngestStatus(StrEnum):
    PENDING = "pending"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
```

### 5.2 SSE Streaming — No Real-time Chunk Emission

**Severity**: Low (by design)
**Observation**: The SSE stream (`/frontend/execute/stream`) emits **whole-artifact** events via `ClientEventKind.ARTIFACT`, not per-token or per-chunk streaming. There is no partial content streaming — the `artifact` event arrives only when generation is complete.

For a real-time chat UI that renders tokens as they arrive, the current SSE contract does **not** support this. Two options:

1. **Backend change**: Introduce a new `ClientEventKind.CHUNK` with `ClientChunkPayload { text_chunk: string }` and stream tokens from the LLM adapter.
2. **Frontend workaround**: Accept the full response latency; render a loading state until `completed`.

### 5.3 Run Status Polling vs. WebSocket

**Severity**: Low
**Observation**: Long-running runs (Map-Reduce summarize) are queried via polling (`GET /frontend/runs/{run_id}`). For a production UI:

- Consider adding a WebSocket upgrade endpoint for push-based status updates.
- The current SSE endpoint (`/frontend/execute/stream`) already provides push events for the **initiating** run. Polling is only needed for status queries on runs started by other clients.

### 5.4 `compare_result` Dual Location in UnifiedExecutionResponseBody

**Severity**: Low (documented compat)
**Observation**: `compare_result: CompareResultItem` appears both as a top-level field and inside `artifacts[].metadata.compare_result` (via `StructuredJsonArtifact` with `schema_name="compare.v1"`). The top-level field is a **compatibility projection** — artifacts carry the authoritative data.

```typescript
// Primary (authoritative): find in artifacts
const compareArtifact = response.artifacts.find(
  a => a.kind === "structured_json" && a.content.schema_name === "compare.v1"
);

// Compatibility (deprecated): use top-level field only for quick hacks
const compare = response.compare_result;
```

Frontend should consume `artifacts[]` as the source of truth for structured data.

### 5.5 `SourceState.ingest_status` is Not Emitted in Any Event

**Severity**: Medium
**Observation**: There is no client event type for document ingest progress. The `/ingest` endpoint returns `IngestResponse` synchronously (or near-synchronously) and does not emit progress events for the batch. For large batch ingests, the frontend has no visibility into per-document progress.

If sub-document progress is needed, consider adding:
- `POST /frontend/execute/stream` support for the `ingest` task type, or
- A dedicated `GET /frontend/ingest-runs/{run_id}` polling endpoint with per-source status.

### 5.6 `map_reduce` Summarize — No Phase Granularity in SSE

**Severity**: Low
**Observation**: Map-Reduce summarize executes `summarize_map` and `summarize_reduce` as internal steps, both mapped to `ProgressPhase.GENERATING`. The frontend cannot distinguish "summarizing each chunk group" from "reducing into final summary". If UX requires this distinction, the projector would need a new `ProgressPhase` variant (e.g., `reducing`) and the internal step mapping would need updating.

---

*Last updated: 2026-04-09 — derived from branch `feat/langchain-integration`*
