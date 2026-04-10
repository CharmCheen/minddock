import React, { useEffect } from 'react';
import { useWorkspaceStore } from '../store';
import { SourceService } from '../../../lib/api/services/sources';

export const SourceDetailPanel: React.FC = () => {
  const { 
    selectedDocId, 
    selectedDocDetail, 
    selectedDocChunks, 
    highlightedChunkId, 
    loadingChunks, 
    setDocChunks, 
    setLoadingChunks,
    setHighlightedChunkId
  } = useWorkspaceStore();

  useEffect(() => {
    if (!selectedDocId) return;

    let mounted = true;
    setLoadingChunks(true);
    
    SourceService.getSourceChunks(selectedDocId)
      .then(chunks => {
        if (mounted) {
          setDocChunks(chunks);
          setLoadingChunks(false);
          
          // Auto-scroll to highlighted chunk if it was already selected (e.g. from citation click before load)
          if (highlightedChunkId) {
            setTimeout(() => {
              const el = document.getElementById(`chunk-${highlightedChunkId}`) || document.getElementById(`chunk-idx-${highlightedChunkId}`);
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 100);
          }
        }
      })
      .catch(() => {
        if (mounted) {
          setDocChunks([]);
          setLoadingChunks(false);
        }
      });

    return () => { mounted = false; };
  }, [selectedDocId]);

  // Effect to handle scroll when highlighedChunkId changes after chunks are loaded
  useEffect(() => {
    if (highlightedChunkId && !loadingChunks) {
      const el = document.getElementById(`chunk-${highlightedChunkId}`) || document.getElementById(`chunk-idx-${highlightedChunkId}`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightedChunkId, loadingChunks]);

  if (!selectedDocId || !selectedDocDetail) {
    return (
      <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', background: '#f8fafc', flexDirection: 'column' }}>
        <div style={{ padding: '32px', textAlign: 'center', background: '#fff', borderRadius: '12px', border: '1px dashed #cbd5e1', maxWidth: '300px' }}>
          <div style={{ color: '#94a3b8', fontSize: '32px', marginBottom: '16px' }}>📄</div>
          <div style={{ fontSize: '15px', fontWeight: '600', marginBottom: '8px', color: '#334155' }}>No Document Selected</div>
          <div style={{ fontSize: '13px', color: '#64748b', lineHeight: '1.5' }}>Choose a source from the list on the left to view its details and contents.</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '24px', flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Detail Header */}
      <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', color: '#0f172a' }}>{selectedDocDetail.title || selectedDocId}</h3>
      <div style={{ fontSize: '13px', color: '#64748b', display: 'flex', gap: '16px', flexWrap: 'wrap', borderBottom: '1px solid #f1f5f9', paddingBottom: '16px', marginBottom: '16px' }}>
        <span><strong>ID:</strong> {selectedDocId}</span>
        <span><strong>Category:</strong> {selectedDocDetail.category}</span>
        <span><strong>Status:</strong> {selectedDocDetail.ingest_status || 'unknown'}</span>
        <span><strong>Uploaded:</strong> {new Date(selectedDocDetail.uploaded_at).toLocaleString()}</span>
      </div>
      
      
      {/* Chunk List */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '8px' }}>
        {loadingChunks && (
           <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
             <span className="dot-pulse" style={{ color: '#3b82f6' }}>●●●</span>
             <span style={{ color: '#64748b', fontSize: '13px' }}>Extracting Document Chunks...</span>
           </div>
        )}
        {!loadingChunks && selectedDocChunks.length === 0 && (
          <div style={{ padding: '32px', textAlign: 'center', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ color: '#cbd5e1', fontSize: '24px', marginBottom: '8px' }}>🔍</div>
            <div style={{ color: '#64748b', fontSize: '14px' }}>No chunks available for this document.</div>
          </div>
        )}
        
        {selectedDocChunks.map((chunk) => {
          const isHighlighted = highlightedChunkId === chunk.chunk_id || highlightedChunkId === String(chunk.chunk_index);
          return (
            <div 
              key={chunk.chunk_id}
              id={`chunk-idx-${chunk.chunk_index}`}
              onClick={() => setHighlightedChunkId(chunk.chunk_id)}
              style={{
                background: isHighlighted ? '#fffbeb' : '#f8fafc',
                border: isHighlighted ? '1px solid #fcd34d' : '1px solid #e2e8f0',
                borderRadius: '8px',
                padding: '16px',
                cursor: 'pointer',
                transition: 'all 0.2s ease-in-out',
                boxShadow: isHighlighted ? '0 0 0 2px #fde68a' : 'none'
              }}
            >
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: '600' }}>Chunk #{chunk.chunk_index}</span>
                {chunk.page && <span>Page: {chunk.page}</span>}
              </div>
              <div style={{ fontSize: '13px', color: '#334155', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                {chunk.preview_text}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
