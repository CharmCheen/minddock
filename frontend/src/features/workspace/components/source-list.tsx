import React, { useEffect, useState, useRef } from 'react';
import { SourceService } from '../../../lib/api/services/sources';
import { SourceItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../store';
import { useSettingsStore } from '../../settings/store';
import { useAvailabilityStore } from '../../app/store/availability';

interface AddUrlDialogProps {
  open: boolean;
  onClose: () => void;
  onAdded: () => void;
}

const AddUrlDialog: React.FC<AddUrlDialogProps> = ({ open, onClose, onAdded }) => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleAdd = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      await SourceService.ingestUrls([trimmed]);
      setUrl('');
      onAdded();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message || 'Failed to ingest URL';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      background: 'rgba(0,0,0,0.4)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: '#fff', borderRadius: '12px', padding: '24px',
        width: '420px', maxWidth: '90vw', boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
      }}>
        <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: '600', color: '#0f172a' }}>
          Add URL to Knowledge Base
        </h3>
        <input
          type="url"
          placeholder="https://example.com/article"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !loading && handleAdd()}
          disabled={loading}
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px',
            border: '1px solid #e2e8f0', fontSize: '14px', outline: 'none',
            boxSizing: 'border-box',
            borderColor: error ? '#ef4444' : '#e2e8f0',
          }}
        />
        {error && (
          <div style={{ color: '#ef4444', fontSize: '12px', marginTop: '6px' }}>{error}</div>
        )}
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '16px' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              padding: '8px 16px', borderRadius: '8px', border: '1px solid #e2e8f0',
              background: '#fff', color: '#64748b', fontSize: '13px', cursor: 'pointer',
            }}>
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={loading || !url.trim()}
            style={{
              padding: '8px 16px', borderRadius: '8px', border: 'none',
              background: loading ? '#93c5fd' : '#3b82f6',
              color: '#fff', fontSize: '13px', cursor: loading ? 'not-allowed' : 'pointer',
            }}>
            {loading ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
};

export const SourceList: React.FC = () => {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(false); // start false, only true when actually loading
  const [addUrlOpen, setAddUrlOpen] = useState(false);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  const { selectedDocId, setSelectedDoc, setDrawerOpen } = useWorkspaceStore();
  const { offline } = useSettingsStore();
  const { status, reset } = useAvailabilityStore();
  const abortRef = useRef<AbortController | null>(null);

  const isBackendOnline = status === 'online' && !offline;
  const isChecking = status === 'checking';

  const loadSources = () => {
    // Cancel any in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    SourceService.getSources({ signal: controller.signal })
      .then(data => {
        setSources(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        // Ignore aborted errors — they're expected when switching sources or HMR
        if (err instanceof Error && err.name === 'CanceledError') return;
        setLoading(false);
      });
  };

  const handleRetry = () => {
    reset(); // re-probe backend
  };

  const handleRefresh = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setRefreshingId(docId);
    try {
      await SourceService.reingestSource(docId);
      loadSources();
    } catch {
      // silently fail
    } finally {
      setRefreshingId(null);
    }
  };

  // Load when backend becomes online; don't load when offline/checking
  useEffect(() => {
    if (isBackendOnline) {
      loadSources();
    } else {
      // Cancel any pending load if we went offline
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    }
  }, [isBackendOnline]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#fff' }}>
      {/* Sidebar Header */}
      <div style={{
        padding: '14px 16px',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex', alignItems: 'center', gap: '10px',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: '30px', height: '30px', borderRadius: '8px',
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          color: '#fff', fontSize: '14px', flexShrink: 0,
        }}>
          📚
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '13px', fontWeight: '600', color: '#0f172a' }}>Knowledge Base</div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>{sources.length} source{sources.length !== 1 ? 's' : ''}</div>
        </div>
        <button
          onClick={() => setAddUrlOpen(true)}
          style={{
            padding: '5px 10px', borderRadius: '6px', border: 'none',
            background: '#3b82f6', color: '#fff', fontSize: '12px', cursor: 'pointer',
            fontWeight: '500',
          }}
          title="Add URL"
        >
          + Add
        </button>
      </div>

      <AddUrlDialog open={addUrlOpen} onClose={() => setAddUrlOpen(false)} onAdded={loadSources} />

      {/* Source List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && (
          <div style={{ padding: '32px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
            <svg viewBox="0 0 24 24" width="20" height="20" style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
              <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
            </svg>
            <span style={{ color: '#64748b', fontSize: '12px' }}>Loading sources...</span>
          </div>
        )}

        {isChecking && (
          <div style={{ padding: '32px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
            <svg viewBox="0 0 24 24" width="20" height="20" style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
              <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
            </svg>
            <span style={{ color: '#64748b', fontSize: '12px' }}>Connecting...</span>
          </div>
        )}

        {(offline || status === 'offline') && !isChecking && (
          <div style={{ padding: '32px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: '28px', marginBottom: '10px' }}>🔌</div>
            <div style={{ color: '#ef4444', fontSize: '13px', fontWeight: '600', marginBottom: '4px' }}>Backend Offline</div>
            <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '16px' }}>
              The server is not reachable.
            </div>
            <button
              onClick={handleRetry}
              style={{
                padding: '6px 14px', borderRadius: '6px', border: '1px solid #e2e8f0',
                background: '#fff', color: '#3b82f6', fontSize: '12px', cursor: 'pointer', fontWeight: '500',
              }}
            >
              Retry Connection
            </button>
          </div>
        )}

        {!loading && !isChecking && !offline && sources.length === 0 && (
          <div style={{ padding: '32px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', marginBottom: '10px' }}>🗂️</div>
            <div style={{ color: '#475569', fontSize: '13px', fontWeight: '600', marginBottom: '6px' }}>No Sources</div>
            <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '16px' }}>
              Add documents or URLs to start.
            </div>
            <button
              onClick={() => setAddUrlOpen(true)}
              style={{
                padding: '6px 12px', borderRadius: '6px', border: 'none',
                background: '#3b82f6', color: '#fff', fontSize: '12px', cursor: 'pointer', fontWeight: '500',
              }}
            >
              + Add URL
            </button>
          </div>
        )}

        {sources.map(src => {
          const isSelected = selectedDocId === src.doc_id;
          return (
            <div
              key={src.doc_id}
              onClick={() => setSelectedDoc(src.doc_id, src)}
              style={{
                padding: '10px 14px',
                borderBottom: '1px solid #f1f5f9',
                cursor: 'pointer',
                background: isSelected ? '#eff6ff' : '#fff',
                borderLeft: isSelected ? '3px solid #3b82f6' : '3px solid transparent',
                transition: 'background 0.12s',
              }}
              onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = '#f8fafc'; }}
              onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = '#fff'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '5px' }}>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '20px', height: '20px', borderRadius: '4px', flexShrink: 0,
                  background: src.source_type === 'url' ? '#dbeafe' : '#f0fdf4', fontSize: '11px',
                }}>
                  {src.source_type === 'url' ? '🔗' : '📄'}
                </span>
                <span style={{ fontSize: '13px', fontWeight: '500', color: '#1e293b', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {src.title || src.doc_id}
                </span>

                {/* Quick action: view detail */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedDoc(src.doc_id, src);
                    setDrawerOpen(true);
                  }}
                  title="View details"
                  style={{
                    background: 'none', border: 'none',
                    cursor: 'pointer', padding: '2px 4px', borderRadius: '4px',
                    color: isSelected ? '#3b82f6' : '#94a3b8', fontSize: '13px',
                    opacity: isSelected ? 1 : 0.6,
                    flexShrink: 0,
                  }}
                  onMouseOver={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.color = '#3b82f6'; }}
                  onMouseOut={e => { e.currentTarget.style.opacity = isSelected ? '1' : '0.6'; e.currentTarget.style.color = isSelected ? '#3b82f6' : '#94a3b8'; }}
                >
                  📖
                </button>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                  {src.source_type === 'url' && src.domain ? (
                    <span style={{
                      display: 'inline-flex', alignItems: 'center',
                      background: '#dbeafe', color: '#1d4ed8',
                      borderRadius: '4px', padding: '0 5px', fontSize: '10px', fontWeight: '500',
                    }}>
                      🌐 {src.domain}
                    </span>
                  ) : (
                    <span style={{
                      display: 'inline-flex', alignItems: 'center',
                      background: '#f1f5f9', color: '#475569',
                      borderRadius: '4px', padding: '0 5px', fontSize: '10px', fontWeight: '500',
                    }}>
                      📄 {src.source_type}
                    </span>
                  )}
                  <span style={{
                    display: 'inline-flex', alignItems: 'center',
                    background: src.source_state?.ingest_status === 'ready' ? '#dcfce7' : '#fef9c3',
                    color: src.source_state?.ingest_status === 'ready' ? '#15803d' : '#a16207',
                    borderRadius: '4px', padding: '0 5px', fontSize: '10px', fontWeight: '500',
                  }}>
                    {src.source_state?.ingest_status === 'ready' ? '●' : '○'} {src.source_state?.ingest_status || 'unknown'}
                  </span>
                </div>

                {src.source_type === 'url' && (
                  <button
                    onClick={(e) => handleRefresh(src.doc_id, e)}
                    disabled={refreshingId === src.doc_id}
                    title="Refresh"
                    style={{
                      background: 'none', border: 'none', cursor: refreshingId === src.doc_id ? 'not-allowed' : 'pointer',
                      padding: '2px', borderRadius: '3px', color: refreshingId === src.doc_id ? '#94a3b8' : '#64748b', fontSize: '12px',
                    }}
                  >
                    {refreshingId === src.doc_id ? '⏳' : '🔄'}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
