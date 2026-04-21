import { create } from 'zustand';
import { SourceCatalogResponse, SourceChunkResponse } from '../../core/types/api';

interface WorkspaceState {
  selectedDocId: string | null;
  selectedDocDetail: SourceCatalogResponse | null;
  selectedDocChunks: SourceChunkResponse[];
  selectedDocTotalChunks: number;
  highlightedChunkId: string | null;
  loadingChunks: boolean;
  drawerOpen: boolean;

  setSelectedDoc: (docId: string | null, detail: SourceCatalogResponse | null) => void;
  setDocChunks: (chunks: SourceChunkResponse[], totalChunks?: number) => void;
  setHighlightedChunkId: (chunkId: string | null) => void;
  setLoadingChunks: (loading: boolean) => void;
  setDrawerOpen: (open: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedDocId: null,
  selectedDocDetail: null,
  selectedDocChunks: [],
  selectedDocTotalChunks: 0,
  highlightedChunkId: null,
  loadingChunks: false,
  drawerOpen: false,

  setSelectedDoc: (docId, detail) => set({
    selectedDocId: docId,
    selectedDocDetail: detail,
    highlightedChunkId: null,
    selectedDocChunks: [],
    selectedDocTotalChunks: 0,
  }),

  setDocChunks: (chunks, totalChunks = chunks.length) => set({
    selectedDocChunks: chunks,
    selectedDocTotalChunks: totalChunks
  }),

  setHighlightedChunkId: (chunkId) => set({ highlightedChunkId: chunkId }),

  setLoadingChunks: (loading) => set({ loadingChunks: loading }),

  setDrawerOpen: (open) => set({ drawerOpen: open }),
}));
