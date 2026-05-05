import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const USER_PREFERENCE_PROFILE_ID = 'workspace_preference_v1';
export const USER_PREFERENCE_PROFILE_VERSION = '1.0.0';

export type DefaultTaskType = 'auto' | 'chat' | 'summarize' | 'compare';
export type CitationStrictness = 'required' | 'preferred' | 'none';
export type AnswerStyle = 'concise' | 'balanced' | 'detailed';
export type SummarizeMode = 'basic' | 'map_reduce';

export interface UserPreferenceProfile {
  id: string;
  version: string;
  scope: 'workspace_local';
  storage: 'browser_local_storage';
  boundary: 'not_long_term_memory';
  preferences: {
    default_task_type: DefaultTaskType;
    default_top_k: number;
    answer_style: AnswerStyle;
    citation_strictness: CitationStrictness;
    summarize_mode: SummarizeMode;
  };
}

interface WorkspacePreferences {
  showTechnicalCitationMetadata: boolean;
  showWorkflowDetails: boolean;
  density: 'compact' | 'comfortable';
  sourceDrawerDefaultOpen: boolean;
  defaultTaskType: DefaultTaskType;
  defaultTopK: number;
  defaultCitationPolicy: CitationStrictness;
  defaultAnswerStyle: AnswerStyle;
  defaultSummarizeMode: SummarizeMode;

  setShowTechnicalCitationMetadata: (value: boolean) => void;
  setShowWorkflowDetails: (value: boolean) => void;
  setDensity: (value: 'compact' | 'comfortable') => void;
  setSourceDrawerDefaultOpen: (value: boolean) => void;
  setDefaultTaskType: (value: DefaultTaskType) => void;
  setDefaultTopK: (value: number) => void;
  setDefaultCitationPolicy: (value: CitationStrictness) => void;
  setDefaultAnswerStyle: (value: AnswerStyle) => void;
  setDefaultSummarizeMode: (value: SummarizeMode) => void;
}

const STORAGE_KEY = 'minddock-workspace-preferences';

export const useWorkspacePreferences = create<WorkspacePreferences>()(
  persist(
    (set) => ({
      showTechnicalCitationMetadata: false,
      showWorkflowDetails: false,
      density: 'comfortable',
      sourceDrawerDefaultOpen: false,
      defaultTaskType: 'auto',
      defaultTopK: 5,
      defaultCitationPolicy: 'preferred',
      defaultAnswerStyle: 'balanced',
      defaultSummarizeMode: 'basic',

      setShowTechnicalCitationMetadata: (value) =>
        set({ showTechnicalCitationMetadata: value }),
      setShowWorkflowDetails: (value) =>
        set({ showWorkflowDetails: value }),
      setDensity: (value) =>
        set({ density: value }),
      setSourceDrawerDefaultOpen: (value) =>
        set({ sourceDrawerDefaultOpen: value }),
      setDefaultTaskType: (value) =>
        set({ defaultTaskType: value }),
      setDefaultTopK: (value) =>
        set({ defaultTopK: value }),
      setDefaultCitationPolicy: (value) =>
        set({ defaultCitationPolicy: value }),
      setDefaultAnswerStyle: (value) =>
        set({ defaultAnswerStyle: value }),
      setDefaultSummarizeMode: (value) =>
        set({ defaultSummarizeMode: value }),
    }),
    {
      name: STORAGE_KEY,
      partialize: (state) => ({
        showTechnicalCitationMetadata: state.showTechnicalCitationMetadata,
        showWorkflowDetails: state.showWorkflowDetails,
        density: state.density,
        sourceDrawerDefaultOpen: state.sourceDrawerDefaultOpen,
        defaultTaskType: state.defaultTaskType,
        defaultTopK: state.defaultTopK,
        defaultCitationPolicy: state.defaultCitationPolicy,
        defaultAnswerStyle: state.defaultAnswerStyle,
        defaultSummarizeMode: state.defaultSummarizeMode,
      }),
    }
  )
);

export function buildUserPreferenceProfile(state: WorkspacePreferences): UserPreferenceProfile {
  return {
    id: USER_PREFERENCE_PROFILE_ID,
    version: USER_PREFERENCE_PROFILE_VERSION,
    scope: 'workspace_local',
    storage: 'browser_local_storage',
    boundary: 'not_long_term_memory',
    preferences: {
      default_task_type: state.defaultTaskType,
      default_top_k: state.defaultTopK,
      answer_style: state.defaultAnswerStyle,
      citation_strictness: state.defaultCitationPolicy,
      summarize_mode: state.defaultSummarizeMode,
    },
  };
}
