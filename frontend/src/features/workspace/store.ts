import { create } from 'zustand';
import { CitationItem, SourceItem, SourceChunkResponse } from '../../core/types/api';

interface WorkspaceState {
  selectedDocIds: string[];
  selectedDocDetails: SourceItem[];
  selectedDocId: string | null;
  selectedDocDetail: SourceItem | null;
  activeCitation: CitationItem | null;
  selectedDocChunks: SourceChunkResponse[];
  selectedDocTotalChunks: number;
  highlightedChunkId: string | null;
  loadingChunks: boolean;
  drawerOpen: boolean;

  setSelectedDoc: (docId: string | null, detail: SourceItem | null, openDrawer?: boolean) => void;
  setSelectedDocDetail: (detail: SourceItem | null) => void;
  openCitationSource: (citation: CitationItem) => void;
  setActiveCitation: (citation: CitationItem | null) => void;
  toggleSelectedDoc: (docId: string, detail: SourceItem) => void;
  clearSelectedDocs: () => void;
  clearSelectedDocsById: (docId: string) => void;
  clearSelectedDoc: () => void;
  setDocChunks: (chunks: SourceChunkResponse[], totalChunks?: number) => void;
  setHighlightedChunkId: (chunkId: string | null) => void;
  setLoadingChunks: (loading: boolean) => void;
  setDrawerOpen: (open: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedDocIds: [],
  selectedDocDetails: [],
  selectedDocId: null,
  selectedDocDetail: null,
  activeCitation: null,
  selectedDocChunks: [],
  selectedDocTotalChunks: 0,
  highlightedChunkId: null,
  loadingChunks: false,
  drawerOpen: false,

  setSelectedDoc: (docId, detail, openDrawer?: boolean) => set({
    selectedDocId: docId,
    selectedDocDetail: detail,
    activeCitation: null,
    highlightedChunkId: null,
    selectedDocChunks: [],
    selectedDocTotalChunks: 0,
    drawerOpen: openDrawer ?? false,
  }),

  setSelectedDocDetail: (detail) => set({
    selectedDocDetail: detail,
  }),

  openCitationSource: (citation) => set({
    selectedDocId: citation.doc_id || null,
    selectedDocDetail: citation.doc_id
      ? {
          doc_id: citation.doc_id,
          source: citation.source || citation.title || citation.doc_id,
          source_type: 'file',
          title: citation.title || citation.source || citation.doc_id,
          chunk_count: 0,
          sections: citation.section ? [citation.section] : [],
          pages: citation.page_num != null ? [citation.page_num] : citation.page != null ? [citation.page] : [],
          requested_url: null,
          final_url: null,
          source_state: null,
          domain: null,
          description: null,
        }
      : null,
    activeCitation: citation,
    highlightedChunkId: citation.chunk_index != null
      ? String(citation.chunk_index)
      : citation.chunk_id?.split(':').pop() ?? citation.chunk_id ?? null,
    selectedDocChunks: [],
    selectedDocTotalChunks: 0,
    drawerOpen: true,
  }),

  setActiveCitation: (citation) => set({
    activeCitation: citation,
  }),

  toggleSelectedDoc: (docId, detail) => set((state) => {
    const exists = state.selectedDocIds.includes(docId);
    if (exists) {
      const nextSelectedDocIds = state.selectedDocIds.filter((id) => id !== docId);
      const nextSelectedDocDetails = state.selectedDocDetails.filter((item) => item.doc_id !== docId);
      const shouldClearSingleSelection = !state.drawerOpen && state.selectedDocId === docId && nextSelectedDocIds.length === 0;
      return {
        selectedDocIds: nextSelectedDocIds,
        selectedDocDetails: nextSelectedDocDetails,
        ...(shouldClearSingleSelection
          ? {
              selectedDocId: null,
              selectedDocDetail: null,
              highlightedChunkId: null,
              selectedDocChunks: [],
              selectedDocTotalChunks: 0,
            }
          : {}),
      };
    }
    return {
      selectedDocIds: [...state.selectedDocIds, docId],
      selectedDocDetails: [...state.selectedDocDetails, detail],
    };
  }),

  clearSelectedDocs: () => set((state) => {
    const shouldClearSingleSelection = !state.drawerOpen && state.selectedDocId !== null;
    return {
      selectedDocIds: [],
      selectedDocDetails: [],
      ...(shouldClearSingleSelection
        ? {
            selectedDocId: null,
            selectedDocDetail: null,
            activeCitation: null,
            highlightedChunkId: null,
            selectedDocChunks: [],
            selectedDocTotalChunks: 0,
          }
        : {}),
    };
  }),

  clearSelectedDocsById: (docId) => set((state) => {
    const nextSelectedDocIds = state.selectedDocIds.filter((id) => id !== docId);
    const nextSelectedDocDetails = state.selectedDocDetails.filter((item) => item.doc_id !== docId);
    const shouldClearSingleSelection = state.selectedDocId === docId;
    return {
      selectedDocIds: nextSelectedDocIds,
      selectedDocDetails: nextSelectedDocDetails,
      ...(shouldClearSingleSelection
        ? {
            selectedDocId: null,
            selectedDocDetail: null,
            activeCitation: null,
            highlightedChunkId: null,
            selectedDocChunks: [],
            selectedDocTotalChunks: 0,
          }
        : {}),
    };
  }),

  clearSelectedDoc: () => set({
    selectedDocIds: [],
    selectedDocDetails: [],
    selectedDocId: null,
    selectedDocDetail: null,
    activeCitation: null,
    highlightedChunkId: null,
    selectedDocChunks: [],
    selectedDocTotalChunks: 0,
    drawerOpen: false,
  }),

  setDocChunks: (chunks, totalChunks = chunks.length) => set({
    selectedDocChunks: chunks,
    selectedDocTotalChunks: totalChunks
  }),

  setHighlightedChunkId: (chunkId) => set({ highlightedChunkId: chunkId }),

  setLoadingChunks: (loading) => set({ loadingChunks: loading }),

  setDrawerOpen: (open) => set({ drawerOpen: open }),
}));
