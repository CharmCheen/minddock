import { apiClient } from '../client';
import { MediaTranscriptConfigResponse } from '../../../core/types/api';

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
};
