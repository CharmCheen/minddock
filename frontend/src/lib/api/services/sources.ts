import { apiClient } from '../client';
import { SourceCatalogResponse, SourceChunkWrapperResponse } from '../../../core/types/api';

export interface SourceServiceOptions {
  signal?: AbortSignal;
}

interface SourceCatalogWrapperResponse {
  items: SourceCatalogResponse[];
  total: number;
}

export const SourceService = {
  async getSources(options?: SourceServiceOptions): Promise<SourceCatalogResponse[]> {
    const { data } = await apiClient.get<SourceCatalogWrapperResponse>('/sources', {
      signal: options?.signal,
    });
    return data.items || [];
  },

  async getSource(docId: string, options?: SourceServiceOptions): Promise<SourceCatalogResponse> {
    const { data } = await apiClient.get<SourceCatalogResponse>(`/sources/${docId}`, {
      signal: options?.signal,
    });
    return data;
  },

  async deleteSource(docId: string, options?: SourceServiceOptions): Promise<void> {
    await apiClient.delete(`/sources/${docId}`, {
      signal: options?.signal,
    });
  },

  async getSourceChunks(docId: string, limit = 100, options?: SourceServiceOptions): Promise<SourceChunkWrapperResponse> {
    const { data } = await apiClient.get<SourceChunkWrapperResponse>(`/sources/${docId}/chunks`, {
      params: { limit, offset: 0 },
      signal: options?.signal,
    });
    return data;
  },

  async ingestUrls(urls: string[], options?: SourceServiceOptions): Promise<void> {
    await apiClient.post('/ingest', { urls, rebuild: false }, {
      signal: options?.signal,
    });
  },

  async reingestSource(docId: string, options?: SourceServiceOptions): Promise<void> {
    await apiClient.post(`/sources/${docId}/reingest`, undefined, {
      signal: options?.signal,
    });
  }
};
