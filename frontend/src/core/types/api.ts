export type ClientEventKind = 
  | 'run_started' 
  | 'progress' 
  | 'artifact' 
  | 'completed' 
  | 'failed';

export type ProgressPhase = 
  | 'preparing' 
  | 'resolving_runtime' 
  | 'retrieving' 
  | 'generating' 
  | 'finalizing';

export type ArtifactKind = 
  | 'text' 
  | 'mermaid' 
  | 'structured_json';

export interface CitationItem {
  doc_id: string;
  chunk_id: string;
  source?: string;
  snippet?: string;
  page?: number | null;
  anchor?: string | null;
  title?: string | null;
  section?: string | null;
  location?: string | null;
  ref?: string | null;
  inline_ref?: string | null;
  chunk_index?: number;
  page_num?: number | null;
  hit_chunk_id?: string | null;
  window_chunk_ids?: string[];
  page_start?: number | null;
  page_end?: number | null;
  section_title?: string | null;
  block_types?: string[];
  table_id?: string | null;
  hit_order_in_doc?: number | null;
  hit_block_type?: string | null;
  hit_page?: number | null;
  is_windowed?: boolean;
  is_hit_only_fallback?: boolean;
  citation_label?: string | null;
  evidence_preview?: string | null;
  window_chunk_count?: number;
  hit_in_window?: boolean;
  evidence_window_reason?: string | null;
  is_derived?: boolean;
  derived_kind?: string | null;
  derived_from?: string | null;
  derived_basis?: string | null;
  evidence_basis?: string | null;
  transcript_provider?: string | null;
  retrieval_basis?: string | null;
}

export interface ClientRunStartedPayload {
  run_id: string;
}

export interface ClientProgressPayload {
  phase: ProgressPhase;
  message: string;
}

export interface ClientArtifactPayload {
  artifact_index: number;
  artifact: ArtifactResponseItem;
}

export interface ClientCompletedPayload {
  artifact_count: number;
  primary_artifact_kind: string | null;
  partial_failure: boolean;
}

export interface ClientFailedPayload {
  detail?: string;
  message?: string;
  error?: string;
}

export interface ClientEvent {
  event: ClientEventKind;
  data:
    | ClientRunStartedPayload
    | ClientProgressPayload
    | ClientArtifactPayload
    | ClientCompletedPayload
    | ClientFailedPayload;
  // Backend sends run_id at top level of ClientEventResponseItem
  run_id?: string;
}

export interface ArtifactResponseItem {
  artifact_id: string;
  kind: ArtifactKind;
  title: string | null;
  content: Record<string, unknown>;
  metadata: Record<string, unknown>;
  citations?: CitationItem[];
}

export interface UnifiedExecutionRequestBody {
  task_type?: string;
  user_input: string;
  top_k: number;
  filters?: {
    source?: string | string[];
  };
  output_mode: string;
  citation_policy: string;
  conversation_metadata?: Record<string, unknown>;
  task_options?: Record<string, unknown>;
}

export interface SourceStateItem {
  doc_id: string;
  source: string;
  current_version: string | null;
  content_hash: string | null;
  last_ingested_at: string | null;
  chunk_count: number;
  ingest_status: string | null;
  error_message?: string | null;
}

export interface SourceItem {
  doc_id: string;
  source: string;
  source_type: string;
  title: string;
  chunk_count: number;
  sections: string[];
  pages: number[];
  requested_url: string | null;
  final_url: string | null;
  source_state: SourceStateItem | null;
  domain: string | null;
  description: string | null;
  representative_metadata?: Record<string, unknown>;
}

export interface SourceCatalogResponse {
  items: SourceItem[];
  total: number;
}

export interface FailedSourceItem {
  source: string;
  source_type: string;
  reason: string;
}

export interface IngestResponse {
  documents: number;
  chunks: number;
  ingested_sources: string[];
  failed_sources: FailedSourceItem[];
  partial_failure: boolean;
}

export interface SourceDetailResponse {
  found: boolean;
  item: SourceItem | null;
  representative_metadata: Record<string, unknown>;
  admin_metadata: Record<string, unknown>;
}

export interface SourceChunkResponse {
  doc_id: string;
  chunk_id: string;
  chunk_index: number;
  preview_text: string;
  page?: number;
  location?: string;
  metadata?: Record<string, unknown>;
  admin_metadata?: Record<string, unknown>;
}

export interface SourceChunkWrapperResponse {
  found: boolean;
  chunks: SourceChunkResponse[];
  total_chunks: number;
  returned_chunks: number;
  limit: number;
  offset: number;
}

export interface ErrorResponse {
  detail: string;
  category?: string;
}

export interface RuntimeConfigResponse {
  provider: string;
  base_url: string;
  model: string;
  api_key_masked: boolean;
  enabled: boolean;
  config_source: string;
  effective_runtime?: {
    profile_id: string;
    provider_kind: string;
    model_name: string;
    base_url: string | null;
    source: string;
    api_key_masked: boolean;
  } | null;
}

export interface MediaTranscriptConfigResponse {
  enabled: boolean;
  provider: string;
  api_key_configured: boolean;
  base_url: string;
  base_url_configured: boolean;
  model: string;
  timeout_seconds: number;
  capability: string;
  limitations: string[];
  config_source: string;
  local_asr_server_path: string;
  local_asr_host: string;
  local_asr_port: number;
  local_asr_model: string;
  local_asr_device: string;
  local_asr_compute_type: string;
  local_asr_auto_start: boolean;
  local_asr_timeout_seconds: number;
}

export interface MediaTranscriptConfigUpdateRequest {
  provider: "mock" | "api" | "local" | "disabled";
  base_url?: string;
  api_key?: string | null;
  model?: string;
  timeout_seconds?: number;
  enabled?: boolean;
  local_asr_server_path?: string;
  local_asr_host?: string;
  local_asr_port?: number;
  local_asr_model?: string;
  local_asr_device?: string;
  local_asr_compute_type?: string;
  local_asr_auto_start?: boolean;
  local_asr_timeout_seconds?: number;
}

export interface MediaTranscriptConfigTestResponse {
  success: boolean;
  message: string;
  error_kind?: string | null;
}

export interface LocalAsrStatusResponse {
  status: string;
  provider: string;
  enabled: boolean;
  base_url: string;
  health_url: string;
  model: string;
  message: string;
}

export interface LocalAsrModelStatusResponse {
  status: string;
  model?: string;
  resolved_model?: string;
  model_path?: string;
  requested_device?: string;
  actual_device?: string;
  compute_type?: string;
  base_url?: string;
  message?: string;
}

export interface RuntimeConfigUpdateRequest {
  provider: string;
  base_url: string;
  api_key?: string;
  model: string;
  enabled: boolean;
}

export interface RuntimeConfigTestRequest {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
}

export interface RuntimeConfigTestResponse {
  success: boolean;
  message: string;
  error_kind: string | null;
}

export interface CancelRunResponse {
  run_id: string;
  status: string;
  cancellation_requested: boolean;
  accepted: boolean;
  detail: string;
}

export interface SourceHandlerConfigField {
  name: string;
  type: string;
  required: boolean;
  default: unknown | null;
  choices: string[];
  min_value: number | null;
  max_value: number | null;
  description: string;
}

export interface SourceSkillItem {
  id: string;
  name: string;
  kind: string;
  version: string;
  status: string;
  description: string;
  input_kinds: string[];
  output_type: string;
  source_media: string | null;
  source_kind: string | null;
  loader_name: string | null;
  handler: string | null;
  capabilities: string[];
  providers: string[];
  limitations: string[];
  permissions: string[];
  safety_notes: string[];
  handler_name: string | null;
  config_schema: SourceHandlerConfigField[];
  config_keys: string[];
  bindable: boolean;
  executable: boolean;
  enabled: boolean;
  origin: string;
  trusted: boolean;
  built_in: boolean;
  category: string;
  supported_extensions: string[];
  supported_mime_types: string[];
  control_plane: string;
  extension_model: string;
  future_market_ready: boolean;
  market_boundary: string;
  installable: boolean;
  remote_install_supported: boolean;
  arbitrary_code_execution: boolean;
}

export interface SourceSkillListResponse {
  items: SourceSkillItem[];
  total: number;
}

export interface SourceSkillValidationResponse {
  ok: boolean;
  skill_id: string | null;
  errors: string[];
  warnings: string[];
  executable: boolean;
  reason: string;
  skill: SourceSkillItem | null;
}
