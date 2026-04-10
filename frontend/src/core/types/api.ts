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
  chunk_id?: string;
  chunk_index: number;
  inline_ref: string;
  page_num?: number;
  snippet?: string;
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
  task_type: string;
  user_input: string;
  top_k: number;
  output_mode: string;
  citation_policy: string;
}

export interface SourceCatalogResponse {
  doc_id: string;
  title: string;
  category: string;
  ingest_status: string | null;
  uploaded_at: string;
}

export interface SourceChunkResponse {
  doc_id: string;
  chunk_id: string;
  chunk_index: number;
  preview_text: string;
  page?: number;
  location?: string;
  metadata?: Record<string, unknown>;
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
