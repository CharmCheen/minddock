import { apiClient } from '../client';
import {
  SourceSkillItem,
  SourceSkillListResponse,
  SourceSkillValidationResponse,
} from '../../../core/types/api';

export const SkillService = {
  async listSourceSkills(): Promise<SourceSkillItem[]> {
    const { data } = await apiClient.get<SourceSkillListResponse>('/frontend/source-skills');
    return data.items || [];
  },

  async getSourceSkill(id: string): Promise<SourceSkillItem> {
    const { data } = await apiClient.get<SourceSkillItem>(`/frontend/source-skills/${encodeURIComponent(id)}`);
    return data;
  },

  async validateSourceSkillManifest(manifest: Record<string, unknown>): Promise<SourceSkillValidationResponse> {
    const { data } = await apiClient.post<SourceSkillValidationResponse>('/frontend/source-skills/validate', { manifest });
    return data;
  },

  async registerSourceSkillManifest(manifest: Record<string, unknown>): Promise<SourceSkillValidationResponse> {
    const { data } = await apiClient.post<SourceSkillValidationResponse>('/frontend/source-skills/register', { manifest });
    return data;
  },

  async enableLocalSourceSkill(id: string): Promise<SourceSkillValidationResponse> {
    const { data } = await apiClient.post<SourceSkillValidationResponse>(`/frontend/source-skills/${encodeURIComponent(id)}/enable`);
    return data;
  },

  async disableLocalSourceSkill(id: string): Promise<SourceSkillValidationResponse> {
    const { data } = await apiClient.post<SourceSkillValidationResponse>(`/frontend/source-skills/${encodeURIComponent(id)}/disable`);
    return data;
  },
};
