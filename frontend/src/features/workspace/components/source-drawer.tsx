import React, { useEffect } from 'react';
import { useWorkspaceStore } from '../store';
import { SourceService } from '../../../lib/api/services/sources';
import { useAvailabilityStore } from '../../app/store/availability';
import { IconLink, IconFileText, IconPlug, IconX } from '../../../components/ui/icons';
import { SourceItem } from '../../../core/types/api';

const EXTRACTION_WARNING_TEXT = 'Extraction may be incomplete. This page may require JavaScript rendering or contain little readable text.';
const LOW_TEXT_CHAR_THRESHOLD = 300;
const QUALITY_IMPACTING_EXTRACTION_WARNINGS = new Set(['empty_main_text', 'non_html_content_type']);

function metadataString(metadata: Record<string, unknown> | undefined, key: string): string {
  const value = metadata?.[key];
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function hasUrlExtractionWarning(source: SourceItem | null): boolean {
  if (!source || source.source_type !== 'url' || source.source_state?.ingest_status !== 'ready') {
    return false;
  }
  const metadata = source.representative_metadata || {};
  const warnings = metadataString(metadata, 'extraction_warnings') || metadataString(metadata, 'loader_warnings');
  const warningCodes = warnings
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  if (warningCodes.some((code) => QUALITY_IMPACTING_EXTRACTION_WARNINGS.has(code))) {
    return true;
  }
  const quality = metadataString(metadata, 'extraction_quality');
  if (quality && !['ok', 'good'].includes(quality)) {
    return true;
  }
  const charCount = Number(metadataString(metadata, 'extracted_char_count'));
  return Number.isFinite(charCount) && charCount > 0 && charCount < LOW_TEXT_CHAR_THRESHOLD;
}

function mediaMetadata(source: SourceItem | null): {
  label: string;
  transcriptProvider: string;
  mediaFilename: string;
  sidecarFilename: string;
  loaderName: string;
  retrievalBasis: string;
} | null {
  if (!source || source.source_state?.ingest_status !== 'ready') {
    return null;
  }
  const metadata = source.representative_metadata || {};
  const sourceMedia = metadataString(metadata, 'source_media').toLowerCase();
  if (sourceMedia !== 'video' && sourceMedia !== 'audio') {
    return null;
  }
  return {
    label: sourceMedia === 'video' ? 'Video source' : 'Audio source',
    transcriptProvider: metadataString(metadata, 'transcript_provider'),
    mediaFilename: metadataString(metadata, 'media_filename'),
    sidecarFilename: metadataString(metadata, 'transcript_sidecar_filename'),
    loaderName: metadataString(metadata, 'loader_name'),
    retrievalBasis: metadataString(metadata, 'retrieval_basis'),
  };
}

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
  const selectedStatus = selectedDocDetail?.source_state?.ingest_status || 'ready';
  const selectedSourceReady = selectedStatus === 'ready';
  const selectedSourceChunksUnavailable = Boolean(selectedDocDetail && !selectedSourceReady);
  const unavailableChunksMessage = selectedStatus === 'failed'
    ? selectedDocDetail?.source_state?.error_message || 'Import failed. Chunks are unavailable for this source.'
    : 'MindDock is still importing this source. Chunks will be available after import completes.';
  const showExtractionWarning = hasUrlExtractionWarning(selectedDocDetail);
  const selectedMediaMetadata = mediaMetadata(selectedDocDetail);

  useEffect(() => {
    if (!drawerOpen || !selectedDocId) return;
    if (
      selectedDocDetail?.doc_id === selectedDocId
      && selectedDocDetail?.source_state !== null
      && selectedDocDetail?.representative_metadata
    ) return;

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
    if (selectedDocDetail?.doc_id === selectedDocId && selectedDocDetail.source_state?.ingest_status !== 'ready') {
      setDocChunks([], 0);
      setLoadingChunks(false);
      return;
    }

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
  }, [drawerOpen, selectedDocId, backendStatus, selectedDocDetail, setDocChunks, setLoadingChunks]);

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
        className="animate-fade-in"
        style={{
          position: 'fixed', inset: 0,
          background: citationMode ? 'transparent' : 'rgba(15, 23, 42, 0.18)',
          pointerEvents: citationMode ? 'none' : 'auto',
          zIndex: 40,
        }}
      />

      {/* Drawer */}
      <div
        data-testid="source-drawer"
        className="animate-drawer-slide"
        style={{
          position: 'fixed',
          top: 0, right: 0, bottom: 0,
          width: '500px',
          maxWidth: '92vw',
          background: 'var(--color-surface)',
          boxShadow: '-10px 0 30px rgba(15, 23, 42, 0.08)',
          zIndex: 50,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'drawerSlideIn 300ms cubic-bezier(0.16, 1, 0.3, 1) forwards',
          borderLeft: '1px solid var(--color-border-subtle)',
        }}
      >
        {/* Drawer Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid var(--color-border-subtle)',
          background: 'var(--color-canvas-subtle)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '36px', height: '36px',
              borderRadius: 'var(--radius-md)',
              background: selectedDocDetail?.source_type === 'url' ? 'var(--color-info-bg)' : 'var(--color-success-bg)',
              color: selectedDocDetail?.source_type === 'url' ? 'var(--color-info-text)' : 'var(--color-success-text)',
              fontSize: '16px',
              flexShrink: 0,
              border: `1px solid ${selectedDocDetail?.source_type === 'url' ? 'var(--color-info-border)' : 'var(--color-success-border)'}`,
            }}>
              {selectedDocDetail?.source_type === 'url' ? <IconLink size={18} /> : <IconFileText size={18} />}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selectedDocDetail?.title || selectedDocId || 'Source Detail'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', marginTop: '2px' }}>
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
              color: 'var(--color-text-tertiary)', fontSize: '20px', cursor: 'pointer',
              padding: '6px', borderRadius: 'var(--radius-md)',
              display: 'flex', alignItems: 'center', lineHeight: 1,
              transition: 'all var(--transition-fast)',
              flexShrink: 0,
            }}
            onMouseOver={e => {
              e.currentTarget.style.background = 'var(--color-canvas)';
              e.currentTarget.style.color = 'var(--color-text-secondary)';
            }}
            onMouseOut={e => {
              e.currentTarget.style.background = 'none';
              e.currentTarget.style.color = 'var(--color-text-tertiary)';
            }}
          >
            <IconX size={20} />
          </button>
        </div>

        {/* Metadata */}
        {selectedDocDetail && (
          <div style={{
            padding: '10px 20px',
            borderBottom: '1px solid var(--color-border-subtle)',
            display: 'flex', gap: '12px', flexWrap: 'wrap',
            fontSize: '11px', color: 'var(--color-text-tertiary)',
            background: 'var(--color-surface)',
            flexShrink: 0,
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ color: 'var(--color-text-tertiary)', fontSize: '11px' }}>📅</span>
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
                <span style={{ color: 'var(--color-text-tertiary)', fontSize: '11px' }}>🌐</span>
                {selectedDocDetail.domain}
              </span>
            )}
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              background: selectedStatus === 'ready' ? 'var(--color-success-bg)' : selectedStatus === 'failed' ? 'var(--color-error-bg)' : 'var(--color-warning-bg)',
              color: selectedStatus === 'ready' ? 'var(--color-success-text)' : selectedStatus === 'failed' ? 'var(--color-error-text)' : 'var(--color-warning-text)',
              borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '11px', fontWeight: 600,
              border: `1px solid ${selectedStatus === 'ready' ? 'var(--color-success-border)' : selectedStatus === 'failed' ? 'var(--color-error-border)' : 'var(--color-warning-border)'}`,
            }}>
              {selectedStatus === 'ready' ? '● ready' : selectedStatus === 'failed' ? '✕ failed' : '○ ' + selectedStatus}
            </span>
          </div>
        )}

        {showExtractionWarning && (
          <div
            data-testid="source-extraction-warning"
            style={{
              padding: '10px 20px',
              borderBottom: '1px solid var(--color-warning-border)',
              background: 'var(--color-warning-bg)',
              color: 'var(--color-warning-text)',
              fontSize: '12px',
              lineHeight: 1.45,
              flexShrink: 0,
            }}
          >
            {EXTRACTION_WARNING_TEXT}
          </div>
        )}

        {selectedMediaMetadata && (
          <div
            data-testid="source-media-metadata"
            style={{
              padding: '10px 20px',
              borderBottom: '1px solid var(--color-border-subtle)',
              background: 'var(--color-surface)',
              display: 'flex',
              flexWrap: 'wrap',
              gap: '8px',
              fontSize: '12px',
              color: 'var(--color-text-secondary)',
              flexShrink: 0,
            }}
          >
            <span style={{
              background: 'var(--color-info-bg)',
              color: 'var(--color-info-text)',
              border: '1px solid var(--color-info-border)',
              borderRadius: 'var(--radius-full)',
              padding: '2px 8px',
              fontWeight: 700,
            }}>
              {selectedMediaMetadata.label}
            </span>
            {selectedMediaMetadata.loaderName && (
              <span style={{
                display: 'inline-flex', alignItems: 'center',
                background: 'var(--color-brand-50)',
                color: 'var(--color-brand-600)',
                border: '1px solid var(--color-brand-200)',
                borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '11px', fontWeight: 600,
              }}>
                {selectedMediaMetadata.loaderName}
              </span>
            )}
            {selectedMediaMetadata.transcriptProvider && (
              <span style={{
                display: 'inline-flex', alignItems: 'center',
                background: 'var(--color-info-bg)',
                color: 'var(--color-info-text)',
                border: '1px solid var(--color-info-border)',
                borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '11px', fontWeight: 600,
              }}>
                Transcript: {selectedMediaMetadata.transcriptProvider}
              </span>
            )}
            {selectedMediaMetadata.retrievalBasis && (
              <span style={{ color: 'var(--color-text-tertiary)' }}>
                Basis: {selectedMediaMetadata.retrievalBasis.replace(/_/g, ' ')}
              </span>
            )}
            {selectedMediaMetadata.mediaFilename && (
              <span>Media: {selectedMediaMetadata.mediaFilename}</span>
            )}
            {selectedMediaMetadata.sidecarFilename && (
              <span>Sidecar: {selectedMediaMetadata.sidecarFilename}</span>
            )}
          </div>
        )}

        {/* Citation Context Panel */}
        {activeCitation && activeCitation.doc_id === selectedDocId && (
          <div
            data-testid="citation-detail-panel"
            style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--color-brand-200)',
              background: 'var(--color-brand-50)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
              flexShrink: 0,
            }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}>
              <div style={{
                fontSize: '11px',
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                color: 'var(--color-brand-600)',
              }}>
                Citation Context
              </div>
              <div style={{
                display: 'flex',
                gap: '8px',
                flexWrap: 'wrap',
                fontSize: '11px',
                color: 'var(--color-text-tertiary)',
              }}>
                {(activeCitation.page_num != null || activeCitation.page != null) && (
                  <span style={{ background: 'var(--color-surface)', padding: '2px 8px', borderRadius: 'var(--radius-full)', border: '1px solid var(--color-border-subtle)' }}>
                    Page {activeCitation.page_num ?? activeCitation.page}
                  </span>
                )}
                {activeCitation.section && <span style={{ background: 'var(--color-surface)', padding: '2px 8px', borderRadius: 'var(--radius-full)', border: '1px solid var(--color-border-subtle)' }}>{activeCitation.section}</span>}
                {activeCitation.location && <span style={{ background: 'var(--color-surface)', padding: '2px 8px', borderRadius: 'var(--radius-full)', border: '1px solid var(--color-border-subtle)' }}>{activeCitation.location}</span>}
              </div>
            </div>

            <div data-testid="citation-detail-title" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-text-primary)' }}>
              {activeCitation.title || activeCitation.source || selectedDocDetail?.title || selectedDocId}
            </div>

            {activeCitation.snippet && (
              <div data-testid="citation-detail-snippet" style={{
                fontSize: '12px',
                lineHeight: '1.6',
                color: 'var(--color-text-secondary)',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 12px',
                borderLeft: '3px solid var(--color-brand-500)',
              }}>
                {activeCitation.snippet}
              </div>
            )}
          </div>
        )}

        {/* Chunk List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 20px', display: 'flex', flexDirection: 'column', gap: '10px', background: 'var(--color-canvas-subtle)' }}>
          {backendStatus !== 'online' && (
            <div style={{
              padding: '24px',
              textAlign: 'center',
              background: 'var(--color-error-bg)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--color-error-border)',
            }}>
              <div style={{ color: 'var(--color-error-text)', fontSize: '24px', marginBottom: '8px' }}>
                <IconPlug size={24} />
              </div>
              <div style={{ color: 'var(--color-error-text)', fontSize: '14px', fontWeight: 700, marginBottom: '4px' }}>Backend Offline</div>
              <div style={{ color: 'var(--color-text-tertiary)', fontSize: '13px' }}>Start the backend or retry connection to load chunks</div>
            </div>
          )}

          {backendStatus === 'online' && loadingChunks && (
            <div style={{
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '12px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border-subtle)',
              borderRadius: 'var(--radius-lg)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <svg viewBox="0 0 24 24" width="24" height="24" style={{ animation: 'spin 1s linear infinite', color: 'var(--color-brand-500)' }}>
                <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
              </svg>
              <span style={{ color: 'var(--color-text-tertiary)', fontSize: '13px' }}>Extracting chunks...</span>
            </div>
          )}

          {backendStatus === 'online' && !loadingChunks && selectedDocChunks.length === 0 && (
            <div style={{
              padding: '24px',
              textAlign: 'center',
              background: 'var(--color-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--color-border-subtle)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{ color: 'var(--color-text-tertiary)', fontSize: '24px', marginBottom: '8px' }}>📭</div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: '14px', fontWeight: selectedSourceChunksUnavailable ? 700 : 400 }}>
                {selectedSourceChunksUnavailable ? 'Chunks unavailable' : 'No chunks available'}
              </div>
              {selectedSourceChunksUnavailable && (
                <div style={{ color: selectedStatus === 'failed' ? 'var(--color-error-text)' : 'var(--color-text-tertiary)', fontSize: '12px', lineHeight: 1.5, marginTop: '8px' }}>
                  {unavailableChunksMessage}
                </div>
              )}
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
                  background: isHighlighted ? '#fffbeb' : 'var(--color-surface)',
                  border: isHighlighted ? '1px solid #fcd34d' : '1px solid var(--color-border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                  cursor: 'pointer',
                  transition: 'all var(--transition-fast)',
                  boxShadow: isHighlighted ? '0 0 0 2px rgba(252, 211, 77, 0.18), var(--shadow-sm)' : 'var(--shadow-sm)',
                }}
                onMouseEnter={e => {
                  if (!isHighlighted) {
                    e.currentTarget.style.borderColor = 'var(--color-border-default)';
                    e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                  }
                }}
                onMouseLeave={e => {
                  if (!isHighlighted) {
                    e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
                    e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
                  }
                }}
              >
                <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>#{chunk.chunk_index}</span>
                  {chunk.page && <span style={{ fontWeight: 500 }}>Page {chunk.page}</span>}
                </div>
                <div style={{ fontSize: '13px', color: 'var(--color-text-secondary)', lineHeight: '1.65', whiteSpace: 'pre-wrap' }}>
                  {chunk.preview_text.length > 220 ? chunk.preview_text.slice(0, 220) + '…' : chunk.preview_text}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};
