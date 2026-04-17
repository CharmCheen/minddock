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
      <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', background: '#f8fafc', flexDirection: 'column', padding: '24px' }}>
        <div style={{
          padding: '40px 32px', textAlign: 'center',
          background: '#fff', borderRadius: '16px',
          border: '1px solid #e2e8f0',
          maxWidth: '320px', width: '100%',
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
        }}>
          <div style={{
            width: '56px', height: '56px', borderRadius: '14px',
            background: 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 20px auto', fontSize: '28px'
          }}>
            📋
          </div>
          <div style={{ fontSize: '15px', fontWeight: '600', marginBottom: '8px', color: '#1e293b' }}>No Source Selected</div>
          <div style={{ fontSize: '13px', color: '#64748b', lineHeight: '1.6' }}>
            Select a source from the left panel to preview its content and metadata.
          </div>
          <div style={{ marginTop: '20px', padding: '12px 16px', background: '#f8fafc', borderRadius: '10px', fontSize: '12px', color: '#64748b', textAlign: 'left' }}>
            <div style={{ fontWeight: '600', marginBottom: '6px', color: '#475569' }}>💡 Tip</div>
            Use <strong>+ Add URL</strong> to ingest web pages as knowledge sources.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '24px', flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.03)' }}>
      {/* Detail Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '12px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '40px',
          height: '40px',
          borderRadius: '10px',
          background: selectedDocDetail.category === 'url' ? '#dbeafe' : '#f0fdf4',
          color: selectedDocDetail.category === 'url' ? '#1d4ed8' : '#10b981',
          fontSize: '20px',
          flexShrink: 0
        }}>
          {selectedDocDetail.category === 'url' ? '🔗' : '📄'}
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: '0 0 4px 0', fontSize: '16px', color: '#0f172a', fontWeight: '600' }}>{selectedDocDetail.title || selectedDocId}</h3>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Source type badge */}
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '3px',
              background: selectedDocDetail.category === 'url' ? '#dbeafe' : '#f1f5f9',
              color: selectedDocDetail.category === 'url' ? '#1d4ed8' : '#475569',
              borderRadius: '5px', padding: '1px 7px', fontSize: '11px', fontWeight: '600',
            }}>
              {selectedDocDetail.category === 'url' ? '🌐 URL' : '📄 File'}
            </span>
            {selectedDocDetail.domain && (
              <span style={{ fontSize: '12px', color: '#64748b' }}>{selectedDocDetail.domain}</span>
            )}
          </div>
        </div>
      </div>
      {/* Metadata strip */}
      <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', gap: '16px', flexWrap: 'wrap', borderBottom: '1px solid #f1f5f9', paddingBottom: '12px', marginBottom: '16px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{color:'#94a3b8', fontSize:'11px'}}>📅</span>
          {new Date(selectedDocDetail.uploaded_at).toLocaleDateString()}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{color:'#94a3b8', fontSize:'11px'}}>📦</span>
          {selectedDocChunks.length} chunks
        </span>
        {selectedDocDetail.ingest_status && (
          <span style={{
            display: 'inline-flex', alignItems: 'center',
            background: selectedDocDetail.ingest_status === 'ready' ? '#dcfce7' : '#fef9c3',
            color: selectedDocDetail.ingest_status === 'ready' ? '#15803d' : '#a16207',
            borderRadius: '5px', padding: '1px 7px', fontSize: '11px', fontWeight: '500',
          }}>
            {selectedDocDetail.ingest_status === 'ready' ? '● ready' : '○ ' + selectedDocDetail.ingest_status}
          </span>
        )}
      </div>
      
      
      {/* Chunk List */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '8px' }}>
        {loadingChunks && (
           <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
             <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px' }}>
               <svg viewBox="0 0 24 24" width="24" height="24" style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }}>
                 <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                 <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
               </svg>
             </div>
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
                borderRadius: '12px',
                padding: '16px',
                cursor: 'pointer',
                transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                boxShadow: isHighlighted ? '0 0 0 2px rgba(252, 211, 77, 0.3)' : 'none'
              }}
              onMouseEnter={(e) => {
                if (!isHighlighted) {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(0,0,0,0.05)';
                  e.currentTarget.style.borderColor = '#cbd5e1';
                }
              }}
              onMouseLeave={(e) => {
                if (!isHighlighted) {
                  e.currentTarget.style.transform = 'none';
                  e.currentTarget.style.boxShadow = 'none';
                  e.currentTarget.style.borderColor = '#e2e8f0';
                }
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
