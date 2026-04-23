import { create } from 'zustand';
import { ClientEvent, ArtifactResponseItem, CitationItem } from '../../core/types/api';

interface AgentState {
  status: 'idle' | 'running' | 'cancelling' | 'cancelled' | 'completed' | 'failed';
  taskType: 'chat' | 'summarize' | 'compare';
  runId: string | null;
  currentUserQuery: string | null;
  events: ClientEvent[];
  artifacts: ArtifactResponseItem[];
  citations: CitationItem[];
  error: string | null;
  
  prepareRun: (query: string) => void;
  startRun: (runId: string, query: string) => void;
  appendEvent: (event: ClientEvent) => void;
  appendArtifact: (artifact: ArtifactResponseItem) => void;
  finishRun: () => void;
  failRun: (errorMsg: string) => void;
  requestCancel: () => void;
  markCancelled: (message?: string) => void;
  reset: () => void;
  setTaskType: (type: 'chat' | 'summarize' | 'compare') => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  status: 'idle',
  taskType: 'chat',
  runId: null,
  currentUserQuery: null,
  events: [],
  artifacts: [],
  citations: [],
  error: null,

  prepareRun: (query) => set({ status: 'running', runId: null, currentUserQuery: query, events: [], artifacts: [], citations: [], error: null }),

  startRun: (runId, query) => set({ status: 'running', runId, currentUserQuery: query, error: null }),
  
  appendEvent: (event) => set((state) => ({ 
    events: [...state.events, event] 
  })),

  appendArtifact: (artifact) => set((state) => ({
    artifacts: [...state.artifacts, artifact]
  })),

  finishRun: () => set({ status: 'completed' }),
  
  failRun: (errorMsg) => set({ status: 'failed', error: errorMsg }),

  requestCancel: () => set({ status: 'cancelling', error: null }),

  markCancelled: (message = 'Cancelled by user') => set({ status: 'cancelled', error: message }),
  
  reset: () => set({ status: 'idle', runId: null, currentUserQuery: null, events: [], artifacts: [], citations: [], error: null }),
  
  setTaskType: (type) => set({ taskType: type })
}));
