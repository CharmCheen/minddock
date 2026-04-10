import { apiClient } from '../client';
import { SourceCatalogResponse, SourceChunkResponse, SourceChunkWrapperResponse } from '../../../core/types/api';

export const SourceService = {
  async getSources(): Promise<SourceCatalogResponse[]> {
    const { data } = await apiClient.get<SourceCatalogResponse[]>('/sources');
    return data;
  },
  
  async getSource(docId: string): Promise<SourceCatalogResponse> {
    const { data } = await apiClient.get<SourceCatalogResponse>(`/sources/${docId}`);
    return data;
  },

  async deleteSource(docId: string): Promise<void> {
    await apiClient.delete(`/sources/${docId}`);
  },

  async getSourceChunks(docId: string): Promise<SourceChunkResponse[]> {
    const { data } = await apiClient.get<SourceChunkWrapperResponse>(`/sources/${docId}/chunks`);
    return data.chunks || [];
  }
};
