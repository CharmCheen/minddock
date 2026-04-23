import React, { useEffect } from 'react';
import { useWorkspaceStore } from '../store';
import { SourceService } from '../../../lib/api/services/sources';
import { useAvailabilityStore } from '../../app/store/availability';

export const SourceDrawer: React.FC = () => {
  const {
    selectedDocId,
    selectedDocDetail,
    selectedDocChunks,
    selectedDocTotalChunks,
    highlightedChunkId,
    loadingChunks,
    drawerOpen,
    setDocChunks,
    setLoadingChunks,
    setHighlightedChunkId,
    setDrawerOpen,
  } = useWorkspaceStore();
  const { status: backendStatus } = useAvailabilityStore();

  useEffect(() => {
    if (!drawerOpen || !selectedDocId) return;
    if (backendStatus !== 'online') return;

    let mounted = true;
    const controller = new AbortController();
    setLoadingChunks(true);

    SourceService.getSourceChunks(selectedDocId, 100, { signal: controller.signal })
      .then((wrapper) => {
        if (mounted) {
          setDocChunks(wrapper.chunks || [], wrapper.total_chunks || 0);
          setLoadingChunks(false);

          if (highlightedChunkId) {
            setTimeout(() => {
              const el = document.getElementById(`chunk-${highlightedChunkId}`) || document.getElementById(`chunk-idx-${highlightedChunkId}`);
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 100);
          }
        }
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'CanceledError') return;
        if (mounted) {
          setDocChunks([], 0);
          setLoadingChunks(false);
        }
      });

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [drawerOpen, selectedDocId, backendStatus]);

  useEffect(() => {
    if (highlightedChunkId && !loadingChunks) {
      const el = document.getElementById(`chunk-${highlightedChunkId}`) || document.getElementById(`chunk-idx-${highlightedChunkId}`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightedChunkId, loadingChunks]);

  if (!drawerOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={() => setDrawerOpen(false)}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.3)',
          zIndex: 40,
        }}
      />

      {/* Drawer */}
      <div style={{
        position: 'fixed',
        top: 0, right: 0, bottom: 0,
        width: '480px',
        maxWidth: '90vw',
        background: '#fff',
        boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
        zIndex: 50,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Drawer Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid #e2e8f0',
          background: '#f8fafc',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '32px', height: '32px',
              borderRadius: '8px',
              background: selectedDocDetail?.source_type === 'url' ? '#dbeafe' : '#f0fdf4',
              color: selectedDocDetail?.source_type === 'url' ? '#1d4ed8' : '#10b981',
              fontSize: '16px',
            }}>
              {selectedDocDetail?.source_type === 'url' ? '🔗' : '📄'}
            </div>
            <div>
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#0f172a' }}>
                {selectedDocDetail?.title || selectedDocId || 'Source Detail'}
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                {selectedDocTotalChunks > 0 ? `${selectedDocChunks.length} / ${selectedDocTotalChunks} chunks` : `${selectedDocChunks.length} chunks`}
              </div>
            </div>
          </div>
          <button
            onClick={() => setDrawerOpen(false)}
            style={{
              background: 'none', border: 'none',
              color: '#64748b', fontSize: '20px', cursor: 'pointer',
              padding: '4px 8px', borderRadius: '6px',
              display: 'flex', alignItems: 'center',
            }}
            onMouseOver={e => (e.currentTarget.style.background = '#e2e8f0')}
            onMouseOut={e => (e.currentTarget.style.background = 'none')}
          >
            ×
          </button>
        </div>

        {/* Metadata */}
        {selectedDocDetail && (
          <div style={{
            padding: '12px 20px',
            borderBottom: '1px solid #f1f5f9',
            display: 'flex', gap: '16px', flexWrap: 'wrap',
            fontSize: '12px', color: '#64748b',
            background: '#fff',
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ color: '#94a3b8', fontSize: '11px' }}>📅</span>
              {(() => {
                try {
                  const ts = selectedDocDetail?.source_state?.last_ingested_at;
                  return ts ? new Date(ts).toLocaleDateString() : '—';
                } catch {
                  return '—';
                }
              })()}
            </span>
            {selectedDocDetail.domain && (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ color: '#94a3b8', fontSize: '11px' }}>🌐</span>
                {selectedDocDetail.domain}
              </span>
            )}
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              background: selectedDocDetail.source_state?.ingest_status === 'ready' ? '#dcfce7' : '#fef9c3',
              color: selectedDocDetail.source_state?.ingest_status === 'ready' ? '#15803d' : '#a16207',
              borderRadius: '5px', padding: '1px 7px', fontSize: '11px', fontWeight: '500',
            }}>
              {selectedDocDetail.source_state?.ingest_status === 'ready' ? '● ready' : '○ ' + (selectedDocDetail.source_state?.ingest_status || 'unknown')}
            </span>
          </div>
        )}

        {/* Chunk List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {backendStatus !== 'online' && (
            <div style={{ padding: '32px', textAlign: 'center', background: '#fef2f2', borderRadius: '8px', border: '1px solid #fecaca' }}>
              <div style={{ color: '#ef4444', fontSize: '24px', marginBottom: '8px' }}>🔌</div>
              <div style={{ color: '#dc2626', fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>Backend Offline</div>
              <div style={{ color: '#94a3b8', fontSize: '13px' }}>Start the backend or retry connection to load chunks</div>
            </div>
          )}

          {backendStatus === 'online' && loadingChunks && (
            <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
              <svg viewBox="0 0 24 24" width="24" height="24" style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }}>
                <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
              </svg>
              <span style={{ color: '#64748b', fontSize: '13px' }}>Extracting chunks...</span>
            </div>
          )}

          {backendStatus === 'online' && !loadingChunks && selectedDocChunks.length === 0 && (
            <div style={{ padding: '32px', textAlign: 'center', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#cbd5e1', fontSize: '24px', marginBottom: '8px' }}>📭</div>
              <div style={{ color: '#64748b', fontSize: '14px' }}>No chunks available</div>
            </div>
          )}

          {selectedDocChunks.map((chunk) => {
            const isHighlighted = highlightedChunkId === chunk.chunk_id || highlightedChunkId === String(chunk.chunk_index);
            return (
              <div
                key={chunk.chunk_id}
                id={`chunk-drawer-${chunk.chunk_id}`}
                onClick={() => setHighlightedChunkId(chunk.chunk_id)}
                style={{
                  background: isHighlighted ? '#fffbeb' : '#f8fafc',
                  border: isHighlighted ? '1px solid #fcd34d' : '1px solid #e2e8f0',
                  borderRadius: '10px',
                  padding: '14px 16px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  boxShadow: isHighlighted ? '0 0 0 2px rgba(252, 211, 77, 0.3)' : 'none'
                }}
                onMouseEnter={e => {
                  if (!isHighlighted) {
                    e.currentTarget.style.transform = 'translateY(-1px)';
                    e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)';
                    e.currentTarget.style.borderColor = '#cbd5e1';
                  }
                }}
                onMouseLeave={e => {
                  if (!isHighlighted) {
                    e.currentTarget.style.transform = 'none';
                    e.currentTarget.style.boxShadow = 'none';
                    e.currentTarget.style.borderColor = '#e2e8f0';
                  }
                }}
              >
                <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: '600', fontFamily: 'monospace' }}>#{chunk.chunk_index}</span>
                  {chunk.page && <span>Page {chunk.page}</span>}
                </div>
                <div style={{ fontSize: '13px', color: '#334155', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                  {chunk.preview_text.length > 200 ? chunk.preview_text.slice(0, 200) + '…' : chunk.preview_text}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
