import { apiClient } from '../client';
import type {
  ScheduleCandidateListResponse,
  ScheduleScanRequest,
  ScheduleScanResponse,
  ScheduleStatusUpdateResponse,
  ScheduleSkillRunResponse,
} from '../../../core/types/schedule';

export interface ScheduleServiceOptions {
  signal?: AbortSignal;
}

export const ScheduleCandidateService = {
  async listCandidates(
    status?: string,
    options?: ScheduleServiceOptions,
  ): Promise<ScheduleCandidateListResponse> {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    const { data } = await apiClient.get<ScheduleCandidateListResponse>(
      '/frontend/schedule-candidates',
      { params, signal: options?.signal },
    );
    return data;
  },

  async scan(
    request?: ScheduleScanRequest,
    options?: ScheduleServiceOptions,
  ): Promise<ScheduleScanResponse> {
    const { data } = await apiClient.post<ScheduleScanResponse>(
      '/frontend/schedule-candidates/scan',
      request ?? {},
      { signal: options?.signal },
    );
    return data;
  },

  async confirm(
    candidateId: string,
    options?: ScheduleServiceOptions,
  ): Promise<ScheduleStatusUpdateResponse> {
    const { data } = await apiClient.post<ScheduleStatusUpdateResponse>(
      `/frontend/schedule-candidates/${candidateId}/confirm`,
      undefined,
      { signal: options?.signal },
    );
    return data;
  },

  async dismiss(
    candidateId: string,
    options?: ScheduleServiceOptions,
  ): Promise<ScheduleStatusUpdateResponse> {
    const { data } = await apiClient.post<ScheduleStatusUpdateResponse>(
      `/frontend/schedule-candidates/${candidateId}/dismiss`,
      undefined,
      { signal: options?.signal },
    );
    return data;
  },

  async runSkill(
    request?: ScheduleScanRequest,
    options?: ScheduleServiceOptions,
  ): Promise<ScheduleSkillRunResponse> {
    const { data } = await apiClient.post<ScheduleSkillRunResponse>(
      '/frontend/skills/schedule-extraction/run',
      request ?? {},
      { signal: options?.signal },
    );
    return data;
  },
};
