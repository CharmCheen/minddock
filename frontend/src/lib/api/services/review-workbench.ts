import { apiClient } from '../client';
import { CitationItem } from '../../../core/types/api';

export interface ReviewWorkbenchResponse {
  task_type: string;
  schema_name: string;
  answer_markdown: string;
  payload: {
    schema_name?: string;
    topic: string;
    sources: string[];
    covered_sources: string[];
    overview: string;
    table: { dimension: string; cells: { source: string; point: string; citation: number | null }[] }[];
    takeaways: string[];
    citation_count: number;
    llm_layer?: string;
    insufficient_evidence?: boolean;
  };
  citations: CitationItem[];
  evidence_badge: Record<string, unknown> | null;
  workflow_trace: Record<string, unknown> | null;
  warnings: string[];
}

export async function runReviewWorkbench(
  topic: string,
  sources: string[],
  topK: number,
): Promise<ReviewWorkbenchResponse> {
  const { data } = await apiClient.post<ReviewWorkbenchResponse>('/frontend/review-workbench', {
    topic,
    sources,
    top_k: topK,
  });
  return data;
}
