import React, { useEffect } from 'react';
import { useWorkspaceStore } from '../store';
import { SourceService } from '../../../lib/api/services/sources';
import { useAvailabilityStore } from '../../app/store/availability';

export const SourceDrawer: React.FC = () => {
  const {
    selectedDocId,
    selectedDocDetail,
    activeCitation,
    selectedDocChunks,
    selectedDocTotalChunks,
    highlightedChunkId,
    loadingChunks,
    drawerOpen,
    setDocChunks,
    setLoadingChunks,
    setHighlightedChunkId,
    setSelectedDocDetail,
    setActiveCitation,
    setDrawerOpen,
  } = useWorkspaceStore();
  const { status: backendStatus } = useAvailabilityStore();
  const citationMode = Boolean(activeCitation && activeCitation.doc_id === selectedDocId);

  useEffect(() => {
    if (!drawerOpen || !selectedDocId) return;
    if (selectedDocDetail?.doc_id === selectedDocId && selectedDocDetail?.source_state !== null) return;

    let mounted = true;
    const controller = new AbortController();

    SourceService.getSource(selectedDocId, { signal: controller.signal })
      .then((detail) => {
        if (mounted) {
          setSelectedDocDetail(detail);
        }
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'CanceledError') return;
      });

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [drawerOpen, selectedDocId, selectedDocDetail, setSelectedDocDetail]);

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
              const el = document.querySelector<HTMLElement>(`[data-chunk-id="${highlightedChunkId}"], [data-chunk-index="${highlightedChunkId}"]`);
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
      const el = document.querySelector<HTMLElement>(`[data-chunk-id="${highlightedChunkId}"], [data-chunk-index="${highlightedChunkId}"]`);
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
          background: citationMode ? 'transparent' : 'rgba(15, 23, 42, 0.22)',
          pointerEvents: citationMode ? 'none' : 'auto',
          zIndex: 40,
        }}
      />

      {/* Drawer */}
      <div
        data-testid="source-drawer"
        style={{
        position: 'fixed',
        top: 0, right: 0, bottom: 0,
        width: '500px',
        maxWidth: '92vw',
        background: '#fff',
        boxShadow: '-10px 0 30px rgba(15, 23, 42, 0.12)',
        zIndex: 50,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Drawer Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 22px',
          borderBottom: '1px solid #e5e7eb',
          background: '#fcfdff',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '30px', height: '30px',
              borderRadius: '7px',
              background: selectedDocDetail?.source_type === 'url' ? '#dbeafe' : '#f0fdf4',
              color: selectedDocDetail?.source_type === 'url' ? '#1d4ed8' : '#10b981',
              fontSize: '15px',
            }}>
              {selectedDocDetail?.source_type === 'url' ? '🔗' : '📄'}
            </div>
            <div>
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#0f172a' }}>
                {selectedDocDetail?.title || selectedDocId || 'Source Detail'}
              </div>
              <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                {selectedDocTotalChunks > 0 ? `${selectedDocChunks.length} / ${selectedDocTotalChunks} chunks` : `${selectedDocChunks.length} chunks`}
              </div>
            </div>
          </div>
          <button
            onClick={() => {
              setDrawerOpen(false);
              setActiveCitation(null);
            }}
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
            padding: '12px 22px',
            borderBottom: '1px solid #e5e7eb',
            display: 'flex', gap: '12px', flexWrap: 'wrap',
            fontSize: '11px', color: '#64748b',
            background: '#f8fafc',
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

        {activeCitation && activeCitation.doc_id === selectedDocId && (
          <div
            data-testid="citation-detail-panel"
            style={{
            padding: '16px 22px',
            borderBottom: '1px solid #dbeafe',
            background: '#f8fbff',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}>
              <div style={{
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: '#64748b',
              }}>
                Citation Detail
              </div>
              <div style={{
                display: 'flex',
                gap: '8px',
                flexWrap: 'wrap',
                fontSize: '11px',
                color: '#64748b',
              }}>
                {(activeCitation.page_num != null || activeCitation.page != null) && (
                  <span>Page {activeCitation.page_num ?? activeCitation.page}</span>
                )}
                {activeCitation.section && <span>{activeCitation.section}</span>}
                {activeCitation.location && <span>{activeCitation.location}</span>}
                {activeCitation.anchor && <span>{activeCitation.anchor}</span>}
              </div>
            </div>

            <div data-testid="citation-detail-title" style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
              {activeCitation.title || activeCitation.source || selectedDocDetail?.title || selectedDocId}
            </div>

            {activeCitation.snippet && (
              <div data-testid="citation-detail-snippet" style={{
                fontSize: '12px',
                lineHeight: '1.6',
                color: '#475569',
                background: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                padding: '10px 12px',
              }}>
                {activeCitation.snippet}
              </div>
            )}
          </div>
        )}

        {/* Chunk List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: '12px', background: '#ffffff' }}>
          {backendStatus !== 'online' && (
            <div style={{ padding: '28px', textAlign: 'center', background: '#fef2f2', borderRadius: '10px', border: '1px solid #fecaca' }}>
              <div style={{ color: '#ef4444', fontSize: '24px', marginBottom: '8px' }}>🔌</div>
              <div style={{ color: '#dc2626', fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>Backend Offline</div>
              <div style={{ color: '#94a3b8', fontSize: '13px' }}>Start the backend or retry connection to load chunks</div>
            </div>
          )}

          {backendStatus === 'online' && loadingChunks && (
            <div style={{ padding: '28px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: '10px' }}>
              <svg viewBox="0 0 24 24" width="24" height="24" style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }}>
                <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
              </svg>
              <span style={{ color: '#64748b', fontSize: '13px' }}>Extracting chunks...</span>
            </div>
          )}

          {backendStatus === 'online' && !loadingChunks && selectedDocChunks.length === 0 && (
            <div style={{ padding: '28px', textAlign: 'center', background: '#f8fafc', borderRadius: '10px', border: '1px solid #e5e7eb' }}>
              <div style={{ color: '#cbd5e1', fontSize: '24px', marginBottom: '8px' }}>📭</div>
              <div style={{ color: '#64748b', fontSize: '14px' }}>No chunks available</div>
            </div>
          )}

          {selectedDocChunks.map((chunk) => {
            const isHighlighted = highlightedChunkId === chunk.chunk_id || highlightedChunkId === String(chunk.chunk_index);
            return (
              <div
                key={chunk.chunk_id}
                data-chunk-id={chunk.chunk_id}
                data-chunk-index={String(chunk.chunk_index)}
                onClick={() => setHighlightedChunkId(chunk.chunk_id)}
                style={{
                  background: isHighlighted ? '#fffbeb' : '#ffffff',
                  border: isHighlighted ? '1px solid #fcd34d' : '1px solid #e5e7eb',
                  borderRadius: '10px',
                  padding: '13px 14px',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease',
                  boxShadow: isHighlighted ? '0 0 0 2px rgba(252, 211, 77, 0.18)' : 'none'
                }}
                onMouseEnter={e => {
                  if (!isHighlighted) {
                    e.currentTarget.style.background = '#f8fafc';
                    e.currentTarget.style.boxShadow = '0 1px 3px rgba(15, 23, 42, 0.04)';
                    e.currentTarget.style.borderColor = '#cbd5e1';
                  }
                }}
                onMouseLeave={e => {
                  if (!isHighlighted) {
                    e.currentTarget.style.background = '#ffffff';
                    e.currentTarget.style.boxShadow = 'none';
                    e.currentTarget.style.borderColor = '#e5e7eb';
                  }
                }}
              >
                <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: '600', fontFamily: 'monospace' }}>#{chunk.chunk_index}</span>
                  {chunk.page && <span>Page {chunk.page}</span>}
                </div>
                <div style={{ fontSize: '12.5px', color: '#334155', lineHeight: '1.65', whiteSpace: 'pre-wrap' }}>
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
