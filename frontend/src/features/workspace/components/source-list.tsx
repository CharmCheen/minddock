import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import { SourceService } from '../../../lib/api/services/sources';
import { SourceItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../store';
import { useSettingsStore } from '../../settings/store';
import { useAvailabilityStore } from '../../app/store/availability';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';
import {
  IconBooks,
  IconBookOpen,
  IconRefresh,
  IconPlug,
  IconFolderOpen,
  IconTrash,
} from '../../../components/ui/icons';

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
      background: 'rgba(0,0,0,0.35)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      animation: 'fadeIn 150ms ease forwards',
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'var(--color-surface)', borderRadius: 'var(--radius-lg)', padding: '24px',
        width: '420px', maxWidth: '90vw', boxShadow: 'var(--shadow-xl)',
        animation: 'scaleIn 200ms ease forwards',
        border: '1px solid var(--color-border-subtle)',
      }}>
        <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
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
            width: '100%', padding: '10px 12px', borderRadius: 'var(--radius-md)',
            border: `1px solid ${error ? 'var(--color-error-border)' : 'var(--color-border-subtle)'}`,
            fontSize: '14px', outline: 'none', boxSizing: 'border-box',
            background: 'var(--color-canvas-subtle)', color: 'var(--color-text-primary)',
            transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
          }}
          onFocus={(e) => {
            e.target.style.borderColor = 'var(--color-brand-200)';
            e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.08)';
          }}
          onBlur={(e) => {
            e.target.style.borderColor = error ? 'var(--color-error-border)' : 'var(--color-border-subtle)';
            e.target.style.boxShadow = 'none';
          }}
        />
        {error && (
          <div style={{ color: 'var(--color-error-text)', fontSize: '12px', marginTop: '6px' }}>{error}</div>
        )}
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '16px' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              padding: '8px 16px', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border-subtle)',
              background: 'var(--color-surface)', color: 'var(--color-text-secondary)',
              fontSize: '13px', cursor: 'pointer', fontWeight: 500,
              transition: 'all var(--transition-fast)',
            }}
            onMouseOver={(e) => { e.currentTarget.style.background = 'var(--color-canvas)'; }}
            onMouseOut={(e) => { e.currentTarget.style.background = 'var(--color-surface)'; }}
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={loading || !url.trim()}
            style={{
              padding: '8px 16px', borderRadius: 'var(--radius-md)', border: 'none',
              background: loading ? 'var(--color-brand-200)' : 'var(--color-brand-600)',
              color: '#fff', fontSize: '13px', cursor: loading || !url.trim() ? 'not-allowed' : 'pointer',
              fontWeight: 600, transition: 'all var(--transition-fast)',
            }}
          >
            {loading ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
};

function inferSourceKind(source: string, sourceType: string): { label: string; color: string; bg: string } {
  if (sourceType === 'url') {
    return { label: 'URL', color: '#1d4ed8', bg: '#dbeafe' };
  }
  const lower = source.toLowerCase();
  if (lower.endsWith('.pdf')) return { label: 'PDF', color: '#b91c1c', bg: '#fee2e2' };
  if (lower.endsWith('.md')) return { label: 'MD', color: '#0f766e', bg: '#ccfbf1' };
  if (lower.endsWith('.txt')) return { label: 'TXT', color: '#475569', bg: '#f1f5f9' };
  if (lower.endsWith('.csv')) return { label: 'CSV', color: '#a16207', bg: '#fef9c3' };
  if (/\.(png|jpg|jpeg|webp)$/.test(lower)) return { label: 'Image', color: '#7c3aed', bg: '#ede9fe' };
  return { label: 'File', color: '#475569', bg: '#f1f5f9' };
}

const FILTER_TABS = ['All', 'File', 'URL', 'Image', 'CSV'] as const;
type FilterTab = typeof FILTER_TABS[number];

function matchesFilterTab(src: SourceItem, tab: FilterTab): boolean {
  if (tab === 'All') return true;
  if (tab === 'URL') return src.source_type === 'url';
  if (tab === 'File') return src.source_type === 'file';
  const kind = inferSourceKind(src.source, src.source_type);
  return kind.label === tab;
}

export const SourceList: React.FC = () => {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [addUrlOpen, setAddUrlOpen] = useState(false);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTab, setFilterTab] = useState<FilterTab>('All');
  const [actionError, setActionError] = useState<string | null>(null);

  const { selectedDocIds, toggleSelectedDoc, setSelectedDoc, setDrawerOpen, drawerOpen, clearSelectedDocsById } = useWorkspaceStore();
  const { offline } = useSettingsStore();
  const { status, reset } = useAvailabilityStore();
  const { density, sourceDrawerDefaultOpen } = useWorkspacePreferences();
  const abortRef = useRef<AbortController | null>(null);
  const suppressAutoOpenRef = useRef(false);
  const prevDrawerOpenRef = useRef(drawerOpen);

  useEffect(() => {
    if (prevDrawerOpenRef.current === true && drawerOpen === false) {
      suppressAutoOpenRef.current = true;
    }
    prevDrawerOpenRef.current = drawerOpen;
  }, [drawerOpen]);

  const isBackendOnline = status === 'online' && !offline;
  const isChecking = status === 'checking';

  const loadSources = useCallback(() => {
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
        if (err instanceof Error && err.name === 'CanceledError') return;
        setLoading(false);
      });
  }, []);

  const handleRetry = () => {
    reset();
  };

  const handleReingest = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setActionError(null);
    setRefreshingId(docId);
    try {
      await SourceService.reingestSource(docId);
      loadSources();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to reingest source';
      setActionError(msg);
    } finally {
      setRefreshingId(null);
    }
  };

  const handleDelete = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('Delete this source? This will remove it from the index and cannot be undone.')) {
      return;
    }
    setActionError(null);
    setDeletingId(docId);
    try {
      await SourceService.deleteSource(docId);
      clearSelectedDocsById(docId);
      loadSources();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete source';
      setActionError(msg);
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    if (isBackendOnline) {
      loadSources();
    } else {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    }
  }, [isBackendOnline, loadSources]);

  const filteredSources = useMemo(() => {
    let result = sources;
    if (filterTab !== 'All') {
      result = result.filter((s) => matchesFilterTab(s, filterTab));
    }
    if (!searchQuery.trim()) return result;
    const q = searchQuery.toLowerCase();
    return result.filter(
      (s) =>
        (s.title || '').toLowerCase().includes(q) ||
        s.source.toLowerCase().includes(q) ||
        s.doc_id.toLowerCase().includes(q)
    );
  }, [sources, searchQuery, filterTab]);

  const d = density;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--color-surface)' }}>
      {/* Sidebar Header */}
      <div style={{
        padding: d === 'compact' ? '12px 14px' : '14px 16px',
        borderBottom: '1px solid var(--color-border-subtle)',
        display: 'flex', alignItems: 'center', gap: '10px',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: '32px', height: '32px', borderRadius: 'var(--radius-md)',
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          color: '#fff', fontSize: '14px', flexShrink: 0,
          boxShadow: '0 2px 6px rgba(16, 185, 129, 0.25)',
        }}>
          <IconBooks size={18} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-text-primary)' }}>Knowledge Base</div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', marginTop: '2px' }}>
            {sources.length} source{sources.length !== 1 ? 's' : ''}
            {selectedDocIds.length > 0 && ` · ${selectedDocIds.length} selected`}
          </div>
        </div>
        <button
          onClick={() => setAddUrlOpen(true)}
          style={{
            padding: '6px 12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-subtle)',
            background: 'var(--color-surface)', color: 'var(--color-brand-600)', fontSize: '12px', cursor: 'pointer',
            fontWeight: 600, transition: 'all var(--transition-fast)',
            boxShadow: 'var(--shadow-sm)',
          }}
          title="Add URL"
          onMouseOver={(e) => {
            e.currentTarget.style.background = 'var(--color-brand-50)';
            e.currentTarget.style.borderColor = 'var(--color-brand-200)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = 'var(--color-surface)';
            e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
          }}
        >
          + Add
        </button>
      </div>

      <AddUrlDialog open={addUrlOpen} onClose={() => setAddUrlOpen(false)} onAdded={loadSources} />

      {/* Search */}
      <div style={{ padding: d === 'compact' ? '8px 12px' : '10px 14px', borderBottom: '1px solid var(--color-border-subtle)', background: 'var(--color-canvas-subtle)' }}>
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sources..."
            style={{
              width: '100%',
              padding: '8px 12px 8px 32px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border-subtle)',
              fontSize: '13px',
              outline: 'none',
              boxSizing: 'border-box',
              background: 'var(--color-surface)',
              color: 'var(--color-text-primary)',
              transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = 'var(--color-brand-200)';
              e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.08)';
            }}
            onBlur={(e) => {
              e.target.style.borderColor = 'var(--color-border-subtle)';
              e.target.style.boxShadow = 'none';
            }}
          />
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-tertiary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}>
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: '4px', marginTop: '8px', flexWrap: 'wrap' }}>
          {FILTER_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setFilterTab(tab)}
              style={{
                padding: '3px 10px',
                borderRadius: 'var(--radius-full)',
                border: filterTab === tab ? '1px solid var(--color-brand-200)' : '1px solid var(--color-border-subtle)',
                background: filterTab === tab ? 'var(--color-brand-50)' : 'var(--color-surface)',
                color: filterTab === tab ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)',
                fontSize: '11px',
                fontWeight: filterTab === tab ? 700 : 500,
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {actionError && (
          <div style={{
            marginTop: '8px',
            padding: '8px 10px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-error-bg)',
            border: '1px solid var(--color-error-border)',
            color: 'var(--color-error-text)',
            fontSize: '12px',
          }}>
            {actionError}
          </div>
        )}

        <div style={{
          marginTop: '6px',
          fontSize: '11px',
          color: 'var(--color-text-tertiary)',
          lineHeight: 1.4,
        }}>
          Select sources to focus retrieval; citations can be verified in the drawer.
        </div>
      </div>

      {/* Source List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px' }}>
        {loading && (
          <div style={{ padding: d === 'compact' ? '24px 12px' : '32px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
            <svg viewBox="0 0 24 24" width="20" height="20" style={{ animation: 'spin 1s linear infinite', color: 'var(--color-brand-500)' }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
              <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
            </svg>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '12px' }}>Loading sources...</span>
          </div>
        )}

        {isChecking && (
          <div style={{ padding: d === 'compact' ? '24px 12px' : '32px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
            <svg viewBox="0 0 24 24" width="20" height="20" style={{ animation: 'spin 1s linear infinite', color: 'var(--color-brand-500)' }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
              <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
            </svg>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '12px' }}>Connecting...</span>
          </div>
        )}

        {(offline || status === 'offline') && !isChecking && (
          <div style={{ padding: d === 'compact' ? '24px 12px' : '32px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: '28px', marginBottom: '10px', color: 'var(--color-error-text)' }}>
              <IconPlug size={28} />
            </div>
            <div style={{ color: 'var(--color-error-text)', fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}>Backend Offline</div>
            <div style={{ color: 'var(--color-text-tertiary)', fontSize: '12px', marginBottom: '16px' }}>
              The server is not reachable.
            </div>
            <button
              onClick={handleRetry}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border-subtle)',
                background: 'var(--color-surface)', color: 'var(--color-brand-600)',
                fontSize: '12px', cursor: 'pointer', fontWeight: 600,
                transition: 'all var(--transition-fast)',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.background = 'var(--color-brand-50)';
                e.currentTarget.style.borderColor = 'var(--color-brand-200)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = 'var(--color-surface)';
                e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
              }}
            >
              Retry Connection
            </button>
          </div>
        )}

        {!loading && !isChecking && !offline && filteredSources.length === 0 && (
          <div style={{ padding: d === 'compact' ? '24px 12px' : '32px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: '28px', marginBottom: '10px', color: 'var(--color-text-tertiary)' }}>
              <IconFolderOpen size={28} />
            </div>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>
              {searchQuery || filterTab !== 'All' ? 'No matching sources' : 'No Sources'}
            </div>
            <div style={{ color: 'var(--color-text-tertiary)', fontSize: '12px', marginBottom: '16px' }}>
              {searchQuery || filterTab !== 'All' ? 'Try a different filter or search term.' : 'Add documents or URLs to start.'}
            </div>
            {!searchQuery && filterTab === 'All' && (
              <button
                onClick={() => setAddUrlOpen(true)}
                style={{
                  padding: '6px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-brand-200)',
                  background: 'var(--color-brand-50)', color: 'var(--color-brand-600)',
                  fontSize: '12px', cursor: 'pointer', fontWeight: 600,
                  transition: 'all var(--transition-fast)',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.background = 'var(--color-brand-100)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.background = 'var(--color-brand-50)';
                }}
              >
                + Add URL
              </button>
            )}
          </div>
        )}

        {filteredSources.map(src => {
          const isSelected = selectedDocIds.includes(src.doc_id);
          const kind = inferSourceKind(src.source, src.source_type);
          const isBusy = refreshingId === src.doc_id || deletingId === src.doc_id;
          return (
            <div
              key={src.doc_id}
              onClick={() => {
                const willSelect = !selectedDocIds.includes(src.doc_id);
                toggleSelectedDoc(src.doc_id, src);
                if (willSelect && sourceDrawerDefaultOpen && !suppressAutoOpenRef.current) {
                  setSelectedDoc(src.doc_id, src);
                  setDrawerOpen(true);
                }
              }}
              style={{
                padding: d === 'compact' ? '8px 10px' : '10px 12px',
                marginBottom: '4px',
                borderRadius: 'var(--radius-md)',
                cursor: 'pointer',
                background: isSelected ? 'var(--color-brand-50)' : 'var(--color-surface)',
                border: `1px solid ${isSelected ? 'var(--color-brand-200)' : 'transparent'}`,
                boxShadow: isSelected ? '0 0 0 1px var(--color-brand-200)' : 'none',
                transition: 'all var(--transition-fast)',
              }}
              onMouseEnter={e => {
                if (!isSelected) {
                  e.currentTarget.style.background = 'var(--color-canvas-subtle)';
                  e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
                }
              }}
              onMouseLeave={e => {
                if (!isSelected) {
                  e.currentTarget.style.background = 'var(--color-surface)';
                  e.currentTarget.style.borderColor = 'transparent';
                }
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                {/* Kind icon */}
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '28px', height: '28px', borderRadius: '6px', flexShrink: 0,
                  background: kind.bg, color: kind.color, fontSize: '10px', fontWeight: 700,
                  marginTop: '1px',
                }}>
                  {kind.label}
                </span>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {src.title || src.doc_id}
                    </span>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedDoc(src.doc_id, src);
                        setDrawerOpen(true);
                      }}
                      title="View details"
                      style={{
                        background: 'none', border: 'none',
                        cursor: 'pointer', padding: '2px 6px', borderRadius: '4px',
                        color: isSelected ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)',
                        fontSize: '13px', opacity: isSelected ? 1 : 0.6,
                        flexShrink: 0, transition: 'all var(--transition-fast)',
                      }}
                      onMouseOver={e => {
                        e.currentTarget.style.opacity = '1';
                        e.currentTarget.style.color = 'var(--color-brand-600)';
                        e.currentTarget.style.background = 'var(--color-canvas-subtle)';
                      }}
                      onMouseOut={e => {
                        e.currentTarget.style.opacity = isSelected ? '1' : '0.6';
                        e.currentTarget.style.color = isSelected ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)';
                        e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      <IconBookOpen size={14} />
                    </button>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center',
                        background: src.source_state?.ingest_status === 'ready' ? 'var(--color-success-bg)' : 'var(--color-warning-bg)',
                        color: src.source_state?.ingest_status === 'ready' ? 'var(--color-success-text)' : 'var(--color-warning-text)',
                        borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '10px', fontWeight: 600,
                        border: `1px solid ${src.source_state?.ingest_status === 'ready' ? 'var(--color-success-border)' : 'var(--color-warning-border)'}`,
                      }}>
                        {src.source_state?.ingest_status === 'ready' ? '● ready' : '○ ' + (src.source_state?.ingest_status || 'unknown')}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                      <button
                        onClick={(e) => handleReingest(src.doc_id, e)}
                        disabled={isBusy}
                        title="Reingest"
                        style={{
                          background: 'none', border: 'none', cursor: isBusy ? 'not-allowed' : 'pointer',
                          padding: '6px', borderRadius: '4px', color: isBusy ? 'var(--color-text-tertiary)' : 'var(--color-text-secondary)',
                          fontSize: '12px', transition: 'color var(--transition-fast), background var(--transition-fast)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          minWidth: '24px', minHeight: '24px',
                        }}
                        onMouseOver={(e) => { if (!isBusy) { e.currentTarget.style.color = 'var(--color-brand-600)'; e.currentTarget.style.background = 'var(--color-brand-50)'; } }}
                        onMouseOut={(e) => { e.currentTarget.style.color = isBusy ? 'var(--color-text-tertiary)' : 'var(--color-text-secondary)'; e.currentTarget.style.background = 'transparent'; }}
                      >
                        {refreshingId === src.doc_id ? (
                          <svg viewBox="0 0 24 24" width="12" height="12" style={{ animation: 'spin 1s linear infinite', color: 'var(--color-brand-500)' }}>
                            <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                            <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
                          </svg>
                        ) : (
                          <IconRefresh size={12} />
                        )}
                      </button>
                      <button
                        onClick={(e) => handleDelete(src.doc_id, e)}
                        disabled={isBusy}
                        title="Delete"
                        style={{
                          background: 'none', border: 'none', cursor: isBusy ? 'not-allowed' : 'pointer',
                          padding: '6px', borderRadius: '4px', color: isBusy ? 'var(--color-text-tertiary)' : 'var(--color-text-secondary)',
                          fontSize: '12px', transition: 'color var(--transition-fast), background var(--transition-fast)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          minWidth: '24px', minHeight: '24px',
                        }}
                        onMouseOver={(e) => { if (!isBusy) { e.currentTarget.style.color = 'var(--color-error-text)'; e.currentTarget.style.background = 'var(--color-error-bg)'; } }}
                        onMouseOut={(e) => { e.currentTarget.style.color = isBusy ? 'var(--color-text-tertiary)' : 'var(--color-text-secondary)'; e.currentTarget.style.background = 'transparent'; }}
                      >
                        {deletingId === src.doc_id ? (
                          <svg viewBox="0 0 24 24" width="12" height="12" style={{ animation: 'spin 1s linear infinite', color: 'var(--color-brand-500)' }}>
                            <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" opacity="0.3"/>
                            <path fill="currentColor" d="M12 2v4a6 6 0 006 6h4a10 10 0 01-10-10z"/>
                          </svg>
                        ) : (
                          <IconTrash size={12} />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
