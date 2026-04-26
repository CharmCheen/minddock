import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface WorkspacePreferences {
  showTechnicalCitationMetadata: boolean;
  showWorkflowDetails: boolean;
  density: 'compact' | 'comfortable';
  sourceDrawerDefaultOpen: boolean;
  defaultTaskType: 'auto' | 'chat' | 'summarize' | 'compare';
  defaultTopK: number;
  defaultCitationPolicy: 'required' | 'preferred' | 'none';
  defaultSummarizeMode: 'basic' | 'map_reduce';

  setShowTechnicalCitationMetadata: (value: boolean) => void;
  setShowWorkflowDetails: (value: boolean) => void;
  setDensity: (value: 'compact' | 'comfortable') => void;
  setSourceDrawerDefaultOpen: (value: boolean) => void;
  setDefaultTaskType: (value: 'auto' | 'chat' | 'summarize' | 'compare') => void;
  setDefaultTopK: (value: number) => void;
  setDefaultCitationPolicy: (value: 'required' | 'preferred' | 'none') => void;
  setDefaultSummarizeMode: (value: 'basic' | 'map_reduce') => void;
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
        defaultSummarizeMode: state.defaultSummarizeMode,
      }),
    }
  )
);
