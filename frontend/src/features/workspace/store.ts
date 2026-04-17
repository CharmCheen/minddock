import { create } from 'zustand';
import { ParticipatingSourceItem, SourceCatalogResponse, SourceChunkResponse } from '../../core/types/api';

export type ParticipationOverlayMap = Record<string, ParticipatingSourceItem['participation_state']>;

interface WorkspaceState {
  selectedDocId: string | null;
  selectedDocDetail: SourceCatalogResponse | null;
  selectedDocChunks: SourceChunkResponse[];
  highlightedChunkId: string | null;
  highlightedSentence: string | null;
  loadingChunks: boolean;
  runtimeParticipationByDocId: ParticipationOverlayMap;

  setSelectedDoc: (docId: string | null, detail: SourceCatalogResponse | null) => void;
  setDocChunks: (chunks: SourceChunkResponse[]) => void;
  setHighlightedChunkId: (chunkId: string | null, sentence?: string | null) => void;
  setLoadingChunks: (loading: boolean) => void;
  setParticipationOverlay: (sources?: ParticipatingSourceItem[]) => void;
  clearParticipationOverlay: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedDocId: null,
  selectedDocDetail: null,
  selectedDocChunks: [],
  highlightedChunkId: null,
  highlightedSentence: null,
  loadingChunks: false,
  runtimeParticipationByDocId: {},

  setSelectedDoc: (docId, detail) => set({
    selectedDocId: docId,
    selectedDocDetail: detail,
    // Note: do NOT reset highlightedChunkId/highlightedSentence here.
    // They are managed separately via setHighlightedChunkId and are cleared
    // only when the citation navigation flow explicitly resets them.
    // Keep existing highlight state so it can be restored after new chunks load.
    selectedDocChunks: []
  }),

  setDocChunks: (chunks) => set({ selectedDocChunks: chunks }),

  setHighlightedChunkId: (chunkId, sentence = null) => set({
    highlightedChunkId: chunkId,
    highlightedSentence: sentence
  }),

  setLoadingChunks: (loading) => set({ loadingChunks: loading }),

  setParticipationOverlay: (sources = []) => set({
    runtimeParticipationByDocId: buildParticipationOverlay(sources)
  }),

  clearParticipationOverlay: () => set({ runtimeParticipationByDocId: {} })
}));

export function buildParticipationOverlay(sources: ParticipatingSourceItem[] = []): ParticipationOverlayMap {
  return sources.reduce<ParticipationOverlayMap>((acc, source) => {
    if (!source?.doc_id) return acc;
    acc[source.doc_id] = source.participation_state ?? null;
    return acc;
  }, {});
}
