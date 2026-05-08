export interface ScheduleCandidateItem {
  id: string;
  title: string;
  start_date: string | null;
  start_time: string | null;
  end_date: string | null;
  end_time: string | null;
  date_text: string | null;
  location: string | null;
  description: string | null;
  source_id: string | null;
  doc_id: string | null;
  chunk_id: string | null;
  source: string | null;
  evidence_text: string | null;
  confidence: number;
  status: 'pending' | 'confirmed' | 'dismissed';
  dedup_key: string;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCandidateListResponse {
  items: ScheduleCandidateItem[];
  total: number;
}

export interface ScheduleScanRequest {
  doc_id?: string;
  source?: string;
}

export interface ScheduleScanResponse {
  chunks_scanned: number;
  candidates_extracted: number;
  candidates_added: number;
  candidates_skipped: number;
  elapsed_ms: number;
}

export interface ScheduleStatusUpdateResponse {
  found: boolean;
  candidate: ScheduleCandidateItem | null;
}

export interface ScheduleSkillRunResponse {
  success: boolean;
  skill_id: string;
  scan_result: ScheduleScanResponse;
  summary_text: string;
}
