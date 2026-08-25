import { apiClient } from '../client';

export type CitationExportFormat = 'bibtex' | 'gbt7714' | 'apa';

export interface CitationExportItem {
  index: number;
  text: string;
  missing: string[];
}

export interface CitationExportResponse {
  format: string;
  count: number;
  text: string;
  items: CitationExportItem[];
}

export async function exportCitations(
  format: CitationExportFormat,
  entries: Record<string, unknown>[],
): Promise<CitationExportResponse> {
  const { data } = await apiClient.post<CitationExportResponse>('/frontend/citations/export', {
    format,
    entries,
  });
  return data;
}
