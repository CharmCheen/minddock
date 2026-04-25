import { create } from 'zustand';
import { ClientEvent, ArtifactResponseItem, CitationItem } from '../../core/types/api';
import type { ConversationTurn } from './types';

let turnCounter = 0;

function generateTurnId(): string {
  turnCounter += 1;
  return `turn-${Date.now()}-${turnCounter}`;
}

interface AgentState {
  status: 'idle' | 'running' | 'cancelling' | 'cancelled' | 'completed' | 'failed';
  taskType: 'chat' | 'summarize' | 'compare';
  runId: string | null;
  currentUserQuery: string | null;
  events: ClientEvent[];
  artifacts: ArtifactResponseItem[];
  citations: CitationItem[];
  error: string | null;

  turns: ConversationTurn[];
  activeTurnId: string | null;

  prepareRun: (query: string, options?: { selectedSources?: string[] }) => void;
  startRun: (runId: string, query: string) => void;
  appendEvent: (event: ClientEvent) => void;
  appendArtifact: (artifact: ArtifactResponseItem) => void;
  finishRun: () => void;
  failRun: (errorMsg: string) => void;
  requestCancel: () => void;
  markCancelled: (message?: string) => void;
  reset: () => void;
  setTaskType: (type: 'chat' | 'summarize' | 'compare') => void;
  clearConversation: () => void;
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
  turns: [],
  activeTurnId: null,

  prepareRun: (query, options) =>
    set((state) => {
      const turnId = generateTurnId();
      const newTurn: ConversationTurn = {
        id: turnId,
        taskType: state.taskType,
        query,
        selectedSources: options?.selectedSources ?? [],
        status: 'running',
        artifacts: [],
        citations: [],
        events: [],
        createdAt: new Date().toISOString(),
      };
      return {
        status: 'running',
        runId: null,
        currentUserQuery: query,
        events: [],
        artifacts: [],
        citations: [],
        error: null,
        turns: [...state.turns, newTurn],
        activeTurnId: turnId,
      };
    }),

  startRun: (runId, query) =>
    set((state) => {
      const updatedTurns = state.activeTurnId
        ? state.turns.map((turn) =>
            turn.id === state.activeTurnId ? { ...turn, runId } : turn
          )
        : state.turns;
      return {
        status: 'running',
        runId,
        currentUserQuery: query,
        error: null,
        turns: updatedTurns,
      };
    }),

  appendEvent: (event) =>
    set((state) => {
      const updatedTurns = state.activeTurnId
        ? state.turns.map((turn) =>
            turn.id === state.activeTurnId
              ? { ...turn, events: [...turn.events, event] }
              : turn
          )
        : state.turns;
      return {
        events: [...state.events, event],
        turns: updatedTurns,
      };
    }),

  appendArtifact: (artifact) =>
    set((state) => {
      const updatedTurns = state.activeTurnId
        ? state.turns.map((turn) => {
            if (turn.id !== state.activeTurnId) return turn;
            if (
              artifact.artifact_id &&
              turn.artifacts.some(
                (existing) => existing.artifact_id === artifact.artifact_id
              )
            ) {
              return turn;
            }
            return { ...turn, artifacts: [...turn.artifacts, artifact] };
          })
        : state.turns;

      if (
        artifact.artifact_id &&
        state.artifacts.some(
          (existing) => existing.artifact_id === artifact.artifact_id
        )
      ) {
        return { artifacts: state.artifacts, turns: updatedTurns };
      }
      return {
        artifacts: [...state.artifacts, artifact],
        turns: updatedTurns,
      };
    }),

  finishRun: () =>
    set((state) => {
      const now = new Date().toISOString();
      const updatedTurns = state.activeTurnId
        ? state.turns.map((turn) =>
            turn.id === state.activeTurnId
              ? { ...turn, status: 'completed' as const, completedAt: now }
              : turn
          )
        : state.turns;
      return {
        status: 'completed',
        turns: updatedTurns,
      };
    }),

  failRun: (errorMsg) =>
    set((state) => {
      const now = new Date().toISOString();
      const updatedTurns = state.activeTurnId
        ? state.turns.map((turn) =>
            turn.id === state.activeTurnId
              ? {
                  ...turn,
                  status: 'failed' as const,
                  error: errorMsg,
                  completedAt: now,
                }
              : turn
          )
        : state.turns;
      return {
        status: 'failed',
        error: errorMsg,
        turns: updatedTurns,
      };
    }),

  requestCancel: () => set({ status: 'cancelling', error: null }),

  markCancelled: (message = 'Cancelled by user') =>
    set((state) => {
      const now = new Date().toISOString();
      const updatedTurns = state.activeTurnId
        ? state.turns.map((turn) =>
            turn.id === state.activeTurnId
              ? {
                  ...turn,
                  status: 'cancelled' as const,
                  error: message,
                  completedAt: now,
                }
              : turn
          )
        : state.turns;
      return {
        status: 'cancelled',
        error: message,
        turns: updatedTurns,
      };
    }),

  reset: () =>
    set({
      status: 'idle',
      runId: null,
      currentUserQuery: null,
      events: [],
      artifacts: [],
      citations: [],
      error: null,
      activeTurnId: null,
    }),

  setTaskType: (type) => set({ taskType: type }),

  clearConversation: () =>
    set({
      status: 'idle',
      runId: null,
      currentUserQuery: null,
      events: [],
      artifacts: [],
      citations: [],
      error: null,
      turns: [],
      activeTurnId: null,
    }),
}));
