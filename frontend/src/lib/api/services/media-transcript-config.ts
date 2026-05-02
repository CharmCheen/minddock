import { apiClient } from '../client';
import {
  MediaTranscriptConfigResponse,
  MediaTranscriptConfigUpdateRequest,
  MediaTranscriptConfigTestResponse,
  LocalAsrStatusResponse,
  LocalAsrModelStatusResponse,
} from '../../../core/types/api';

export interface MediaTranscriptServiceOptions {
  signal?: AbortSignal;
}

export const MediaTranscriptConfigService = {
  async getConfig(options?: MediaTranscriptServiceOptions): Promise<MediaTranscriptConfigResponse> {
    const response = await apiClient.get<MediaTranscriptConfigResponse>('/frontend/media-transcript-config', {
      signal: options?.signal,
    });
    return response.data;
  },

  async updateConfig(
    payload: MediaTranscriptConfigUpdateRequest,
    options?: MediaTranscriptServiceOptions,
  ): Promise<MediaTranscriptConfigResponse> {
    const response = await apiClient.put<MediaTranscriptConfigResponse>(
      '/frontend/media-transcript-config',
      payload,
      { signal: options?.signal },
    );
    return response.data;
  },

  async resetConfig(options?: MediaTranscriptServiceOptions): Promise<MediaTranscriptConfigResponse> {
    const response = await apiClient.post<MediaTranscriptConfigResponse>(
      '/frontend/media-transcript-config/reset',
      {},
      { signal: options?.signal },
    );
    return response.data;
  },

  async testConfig(
    payload: MediaTranscriptConfigUpdateRequest,
    options?: MediaTranscriptServiceOptions,
  ): Promise<MediaTranscriptConfigTestResponse> {
    const response = await apiClient.post<MediaTranscriptConfigTestResponse>(
      '/frontend/media-transcript-config/test',
      payload,
      { signal: options?.signal },
    );
    return response.data;
  },

  async checkLocalStatus(options?: MediaTranscriptServiceOptions): Promise<LocalAsrStatusResponse> {
    const response = await apiClient.get<LocalAsrStatusResponse>(
      '/frontend/media-transcript-config/local/status',
      { signal: options?.signal },
    );
    return response.data;
  },

  async startLocalAsr(options?: MediaTranscriptServiceOptions): Promise<LocalAsrStatusResponse> {
    const response = await apiClient.post<LocalAsrStatusResponse>(
      '/frontend/media-transcript-config/local/start',
      {},
      { signal: options?.signal },
    );
    return response.data;
  },

  async checkLocalModelStatus(options?: MediaTranscriptServiceOptions): Promise<LocalAsrModelStatusResponse> {
    const response = await apiClient.get<LocalAsrModelStatusResponse>(
      '/frontend/media-transcript-config/local/model/status',
      { signal: options?.signal },
    );
    return response.data;
  },

  async preloadLocalModel(options?: MediaTranscriptServiceOptions): Promise<LocalAsrModelStatusResponse> {
    const response = await apiClient.post<LocalAsrModelStatusResponse>(
      '/frontend/media-transcript-config/local/model/preload',
      {},
      { signal: options?.signal },
    );
    return response.data;
  },
};
