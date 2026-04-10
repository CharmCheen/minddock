import { create } from 'zustand';
import { SourceCatalogResponse, SourceChunkResponse } from '../../core/types/api';

interface WorkspaceState {
  selectedDocId: string | null;
  selectedDocDetail: SourceCatalogResponse | null;
  selectedDocChunks: SourceChunkResponse[];
  highlightedChunkId: string | null;
  loadingChunks: boolean;

  setSelectedDoc: (docId: string | null, detail: SourceCatalogResponse | null) => void;
  setDocChunks: (chunks: SourceChunkResponse[]) => void;
  setHighlightedChunkId: (chunkId: string | null) => void;
  setLoadingChunks: (loading: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedDocId: null,
  selectedDocDetail: null,
  selectedDocChunks: [],
  highlightedChunkId: null,
  loadingChunks: false,

  setSelectedDoc: (docId, detail) => set({ 
    selectedDocId: docId, 
    selectedDocDetail: detail,
    highlightedChunkId: null,
    // clear chunks while new ones load
    selectedDocChunks: []
  }),
  
  setDocChunks: (chunks) => set({ selectedDocChunks: chunks }),
  
  setHighlightedChunkId: (chunkId) => set({ highlightedChunkId: chunkId }),

  setLoadingChunks: (loading) => set({ loadingChunks: loading })
}));
