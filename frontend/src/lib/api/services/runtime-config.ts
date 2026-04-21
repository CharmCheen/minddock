import { apiClient } from '../client';
import { RuntimeConfigResponse, RuntimeConfigUpdateRequest, RuntimeConfigTestRequest, RuntimeConfigTestResponse } from '../../../core/types/api';

export interface RuntimeServiceOptions {
  signal?: AbortSignal;
}

export const RuntimeConfigService = {
  async getConfig(options?: RuntimeServiceOptions): Promise<RuntimeConfigResponse> {
    const response = await apiClient.get<RuntimeConfigResponse>('/frontend/runtime-config', {
      signal: options?.signal,
    });
    return response.data;
  },

  async updateConfig(config: RuntimeConfigUpdateRequest, options?: RuntimeServiceOptions): Promise<RuntimeConfigResponse> {
    const response = await apiClient.put<RuntimeConfigResponse>('/frontend/runtime-config', config, {
      signal: options?.signal,
    });
    return response.data;
  },

  async testConnection(config: RuntimeConfigTestRequest, options?: RuntimeServiceOptions): Promise<RuntimeConfigTestResponse> {
    const response = await apiClient.post<RuntimeConfigTestResponse>('/frontend/runtime-config/test', config, {
      signal: options?.signal,
    });
    return response.data;
  },

  async resetConfig(options?: RuntimeServiceOptions): Promise<RuntimeConfigResponse> {
    const response = await apiClient.post<RuntimeConfigResponse>('/frontend/runtime-config/reset', undefined, {
      signal: options?.signal,
    });
    return response.data;
  },
};
