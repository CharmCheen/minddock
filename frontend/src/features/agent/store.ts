import { create } from 'zustand';
import { ClientEvent, ArtifactResponseItem, CitationItem } from '../../core/types/api';

interface AgentState {
  status: 'idle' | 'running' | 'completed' | 'failed';
  taskType: 'chat' | 'summarize' | 'compare';
  runId: string | null;
  currentUserQuery: string | null;
  events: ClientEvent[];
  artifacts: ArtifactResponseItem[];
  citations: CitationItem[];
  error: string | null;
  // Workspace boundary expression
  answerMode: 'knowledge_base_only' | 'knowledge_plus_inference';
  contributingSources: string[];  // doc_ids that contributed to current answer

  startRun: (runId: string, query: string) => void;
  appendEvent: (event: ClientEvent) => void;
  appendArtifact: (artifact: ArtifactResponseItem) => void;
  finishRun: () => void;
  failRun: (errorMsg: string) => void;
  reset: () => void;
  setTaskType: (type: 'chat' | 'summarize' | 'compare') => void;
  setAnswerMode: (mode: 'knowledge_base_only' | 'knowledge_plus_inference') => void;
  setContributingSources: (sources: string[]) => void;
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
  answerMode: 'knowledge_base_only',
  contributingSources: [],

  startRun: (runId, query) => set({ status: 'running', runId, currentUserQuery: query, events: [], artifacts: [], citations: [], error: null, answerMode: 'knowledge_base_only', contributingSources: [] }),

  appendEvent: (event) => set((state) => ({
    events: [...state.events, event]
  })),

  appendArtifact: (artifact) => set((state) => ({
    artifacts: [...state.artifacts, artifact]
  })),

  finishRun: () => set({ status: 'completed' }),

  failRun: (errorMsg) => set({ status: 'failed', error: errorMsg }),

  reset: () => set({ status: 'idle', runId: null, currentUserQuery: null, events: [], artifacts: [], citations: [], error: null, answerMode: 'knowledge_base_only', contributingSources: [] }),

  setTaskType: (type) => set({ taskType: type }),

  setAnswerMode: (mode) => set({ answerMode: mode }),

  setContributingSources: (sources) => set({ contributingSources: sources })
}));
