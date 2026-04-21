import { apiClient } from '../client';
import { RuntimeConfigResponse, RuntimeConfigUpdateRequest, RuntimeConfigTestRequest, RuntimeConfigTestResponse } from '../../../core/types/api';

export const RuntimeConfigService = {
  async getConfig(): Promise<RuntimeConfigResponse> {
    const response = await apiClient.get<RuntimeConfigResponse>('/frontend/runtime-config');
    return response.data;
  },

  async updateConfig(config: RuntimeConfigUpdateRequest): Promise<RuntimeConfigResponse> {
    const response = await apiClient.put<RuntimeConfigResponse>('/frontend/runtime-config', config);
    return response.data;
  },

  async testConnection(config: RuntimeConfigTestRequest): Promise<RuntimeConfigTestResponse> {
    const response = await apiClient.post<RuntimeConfigTestResponse>('/frontend/runtime-config/test', config);
    return response.data;
  },

  async resetConfig(): Promise<RuntimeConfigResponse> {
    const response = await apiClient.post<RuntimeConfigResponse>('/frontend/runtime-config/reset');
    return response.data;
  },
};
