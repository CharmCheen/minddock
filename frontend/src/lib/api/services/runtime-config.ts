import { apiClient } from '../client';
import { RuntimeConfigResponse, RuntimeConfigUpdateRequest } from '../../../core/types/api';

export const RuntimeConfigService = {
  async getConfig(): Promise<RuntimeConfigResponse> {
    const response = await apiClient.get<RuntimeConfigResponse>('/frontend/runtime-config');
    return response.data;
  },

  async updateConfig(config: RuntimeConfigUpdateRequest): Promise<RuntimeConfigResponse> {
    const response = await apiClient.put<RuntimeConfigResponse>('/frontend/runtime-config', config);
    return response.data;
  },
};
