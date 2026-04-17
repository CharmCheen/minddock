import React, { useEffect, useState } from 'react';
import { SourceService } from '../../../lib/api/services/sources';
import { SourceCatalogResponse } from '../../../core/types/api';
import { useWorkspaceStore } from '../store';
import { SourceDetailPanel } from './source-detail-panel';

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
  const [sources, setSources] = useState<SourceCatalogResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addUrlOpen, setAddUrlOpen] = useState(false);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  const { selectedDocId, setSelectedDoc, runtimeParticipationByDocId } = useWorkspaceStore();

  const displayedSources = applyParticipationOverlay(sources, runtimeParticipationByDocId);

  const loadSources = () => {
    setLoading(true);
    setError(null);
    SourceService.getSources()
      .then(data => {
        setSources(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : (err as { message?: string })?.message || 'Failed to load sources';
        setError(msg);
        setLoading(false);
      });
  };

  const handleRefresh = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setRefreshingId(docId);
    try {
      await SourceService.reingestSource(docId);
      await loadSources();
    } catch (err: unknown) {
      // silently fail for refresh errors
    } finally {
      setRefreshingId(null);
    }
  };

  useEffect(() => {
    loadSources();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f8fafc' }}>
      <div style={{
        padding: '16px 24px',
        borderBottom: '1px solid #e2e8f0',
        background: '#fff',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '36px',
          height: '36px',
          borderRadius: '10px',
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          color: '#fff',
          fontSize: '18px',
          boxShadow: '0 2px 8px rgba(16, 185, 129, 0.3)'
        }}>
          📚
        </div>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: '#0f172a' }}>Document Workspace</h2>
          <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Manage your knowledge base sources</p>
        </div>
        <button
          onClick={() => setAddUrlOpen(true)}
          style={{
            padding: '6px 14px', borderRadius: '8px', border: 'none',
            background: '#3b82f6', color: '#fff', fontSize: '13px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '4px',
          }}
          title="Add URL"
        >
          + Add URL
        </button>
      </div>
      <AddUrlDialog open={addUrlOpen} onClose={() => setAddUrlOpen(false)} onAdded={loadSources} />
      
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Source List Column */}
        <div style={{ width: '40%', minWidth: '200px', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', background: '#fff' }}>
          <div style={{ padding: '12px 16px', background: '#f1f5f9', fontSize: '13px', fontWeight: '600', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Knowledge Sources
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading && (
              <div style={{ padding: '32px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px' }}>
                  <svg viewBox="0 0 24 24" width="24" height="24" style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }}>
                    <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                    <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
                  </svg>
                </div>
                <span style={{ color: '#64748b', fontSize: '13px' }}>Loading Sources...</span>
              </div>
            )}
            {error && (
              <div style={{ padding: '24px 16px', textAlign: 'center' }}>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '44px', height: '44px', borderRadius: '50%',
                  background: '#fef2f2', marginBottom: '12px', fontSize: '22px'
                }}>
                  ⚠️
                </div>
                <div style={{ color: '#ef4444', fontSize: '14px', fontWeight: '600', marginBottom: '4px' }}>Failed to Load Sources</div>
                <div style={{ color: '#f87171', fontSize: '12px', marginBottom: '16px', lineHeight: '1.5' }}>{error}</div>
                <button
                  onClick={loadSources}
                  style={{
                    padding: '6px 14px', borderRadius: '8px', border: '1px solid #e2e8f0',
                    background: '#fff', color: '#64748b', fontSize: '12px', cursor: 'pointer',
                  }}
                >
                  Try Again
                </button>
              </div>
            )}
            {!loading && !error && sources.length === 0 && (
              <div style={{ padding: '32px 16px', textAlign: 'center' }}>
                <div style={{
                  width: '52px', height: '52px', borderRadius: '12px',
                  background: 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 16px auto', fontSize: '26px'
                }}>
                  🗂️
                </div>
                <div style={{ color: '#475569', fontSize: '14px', fontWeight: '600', marginBottom: '6px' }}>No Sources Yet</div>
                <div style={{ color: '#94a3b8', fontSize: '13px', marginBottom: '20px', lineHeight: '1.5' }}>
                  Add documents or URLs to start building your knowledge base.
                </div>
                <button
                  onClick={() => setAddUrlOpen(true)}
                  style={{
                    padding: '8px 16px', borderRadius: '8px', border: 'none',
                    background: '#3b82f6', color: '#fff', fontSize: '13px',
                    cursor: 'pointer', fontWeight: '500',
                    boxShadow: '0 2px 6px rgba(59, 130, 246, 0.25)',
                  }}
                >
                  + Add URL
                </button>
              </div>
            )}
            {displayedSources.map(src => (
              <div
                key={src.doc_id}
                onClick={() => setSelectedDoc(src.doc_id, src)}
                onMouseEnter={(e) => {
                  if (selectedDocId !== src.doc_id) {
                    e.currentTarget.style.background = '#f8fafc';
                  }
                }}
                onMouseLeave={(e) => {
                  if (selectedDocId !== src.doc_id) {
                    e.currentTarget.style.background = '#fff';
                  }
                }}
                style={{
                  padding: '12px 16px',
                  borderBottom: '1px solid #f1f5f9',
                  cursor: 'pointer',
                  background: selectedDocId === src.doc_id ? '#eff6ff' : '#fff',
                  borderLeft: selectedDocId === src.doc_id ? '3px solid #3b82f6' : '3px solid transparent',
                  transition: 'background 0.15s ease'
                }}
              >
                {/* Row: icon + title */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  {/* Source-type icon */}
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: '22px', height: '22px', borderRadius: '5px', flexShrink: 0,
                    background: src.category === 'url' ? '#dbeafe' : '#f0fdf4',
                    fontSize: '12px',
                  }}>
                    {src.category === 'url' ? '🔗' : '📄'}
                  </span>
                  <span style={{ fontSize: '14px', fontWeight: '500', color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
                    {src.title || src.doc_id}
                  </span>
                </div>
                {/* Row: badges + status + action */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
                  {/* Source-type and domain badge */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                    {src.category === 'url' && src.domain ? (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: '3px',
                        background: '#dbeafe', color: '#1d4ed8',
                        borderRadius: '5px', padding: '1px 6px', fontSize: '11px', fontWeight: '500',
                      }}>
                        🌐 {src.domain}
                      </span>
                    ) : (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center',
                        background: '#f1f5f9', color: '#475569',
                        borderRadius: '5px', padding: '1px 6px', fontSize: '11px', fontWeight: '500',
                      }}>
                        📄 {src.category}
                      </span>
                    )}
                    {/* Status badge */}
                    <span style={{
                      display: 'inline-flex', alignItems: 'center',
                      background: src.ingest_status === 'ready' ? '#dcfce7' : '#fef9c3',
                      color: src.ingest_status === 'ready' ? '#15803d' : '#a16207',
                      borderRadius: '5px', padding: '1px 6px', fontSize: '11px', fontWeight: '500',
                    }}>
                      {src.ingest_status === 'ready' ? '● ready' : '○ ' + (src.ingest_status || 'unknown')}
                    </span>
                    {/* Participation state badge */}
                    {src.participation_state && (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center',
                        background: src.participation_state === 'participating' ? '#dbeafe' :
                                   src.participation_state === 'indexed' ? '#dcfce7' :
                                   src.participation_state === 'excluded' ? '#fee2e2' : '#f1f5f9',
                        color: src.participation_state === 'participating' ? '#1d4ed8' :
                              src.participation_state === 'indexed' ? '#15803d' :
                              src.participation_state === 'excluded' ? '#dc2626' : '#64748b',
                        borderRadius: '5px', padding: '1px 6px', fontSize: '11px', fontWeight: '500',
                      }}>
                        {src.participation_state === 'participating' ? '◉ ' + src.participation_state :
                         src.participation_state === 'indexed' ? '● ' + src.participation_state :
                         src.participation_state === 'excluded' ? '✕ ' + src.participation_state :
                         src.participation_state}
                      </span>
                    )}
                  </div>
                  {/* Refresh button for URL sources */}
                  {src.category === 'url' && (
                    <button
                      onClick={(e) => handleRefresh(src.doc_id, e)}
                      disabled={refreshingId === src.doc_id}
                      title="Refresh URL source"
                      style={{
                        background: 'none', border: 'none',
                        cursor: refreshingId === src.doc_id ? 'not-allowed' : 'pointer',
                        padding: '2px 4px', borderRadius: '4px',
                        color: refreshingId === src.doc_id ? '#94a3b8' : '#3b82f6',
                        fontSize: '14px', lineHeight: 1, display: 'flex', alignItems: 'center',
                      }}
                    >
                      {refreshingId === src.doc_id ? '⏳' : '🔄'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Source Detail Preview */}
        <div style={{ flex: 1, background: '#f8fafc', display: 'flex', flexDirection: 'column', padding: '24px', overflow: 'hidden' }}>
          <SourceDetailPanel />
        </div>
      </div>
    </div>
  );
};

export function applyParticipationOverlay(
  sources: SourceCatalogResponse[],
  overlay: Record<string, SourceCatalogResponse['participation_state']>,
): SourceCatalogResponse[] {
  return sources.map((source) => {
    const nextParticipationState = overlay[source.doc_id];
    if (nextParticipationState === undefined) {
      return source;
    }
    return {
      ...source,
      participation_state: nextParticipationState,
    };
  });
}
