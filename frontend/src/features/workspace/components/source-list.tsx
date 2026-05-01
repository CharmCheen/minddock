import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import axios from 'axios';
import { SourceService } from '../../../lib/api/services/sources';
import { getErrorMessage } from '../../../lib/api/client';
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
  onSubmit: (url: string) => void;
}

const AddUrlDialog: React.FC<AddUrlDialogProps> = ({ open, onClose, onSubmit }) => {
  const [url, setUrl] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const validateUrl = (value: string): string | null => {
    if (!value.trim()) return 'Enter a URL to import.';
    try {
      const parsed = new URL(value.trim());
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        return 'Enter a valid http or https URL.';
      }
    } catch {
      return 'Enter a valid URL.';
    }
    return null;
  };

  const handleAdd = () => {
    const trimmed = url.trim();
    const validationError = validateUrl(trimmed);
    if (validationError) {
      setError(validationError);
      return;
    }
    setUrl('');
    setError(null);
    onClose();
    onSubmit(trimmed);
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
          onChange={(e) => {
            setUrl(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
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
            style={{
              padding: '8px 16px', borderRadius: 'var(--radius-md)', border: 'none',
              background: 'var(--color-brand-600)',
              color: '#fff', fontSize: '13px', cursor: 'pointer',
              fontWeight: 600, transition: 'all var(--transition-fast)',
            }}
          >
            Add
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
  if (/\.(mp3|wav|m4a|aac|flac|ogg)$/.test(lower)) return { label: 'Audio', color: '#c2410c', bg: '#ffedd5' };
  if (/\.(mp4|mov|mkv|webm)$/.test(lower)) return { label: 'Video', color: '#be123c', bg: '#ffe4e6' };
  return { label: 'File', color: '#475569', bg: '#f1f5f9' };
}

const FILTER_TABS = ['All', 'File', 'URL', 'Image', 'CSV', 'Audio', 'Video'] as const;
type FilterTab = typeof FILTER_TABS[number];
type SourceNoticeTone = 'info' | 'success' | 'warning' | 'error';
type PendingSourceStatus = 'importing' | 'still_processing' | 'failed';

interface SourceNotice {
  id: number;
  tone: SourceNoticeTone;
  message: string;
}

interface PendingSourceItem {
  id: string;
  url: string;
  normalizedUrl: string;
  status: PendingSourceStatus;
  failureReason?: string;
}

interface UrlImportPollState {
  active: boolean;
  timerId: number | null;
}

type SourceItemWithOptionalUrlFields = SourceItem & {
  url?: string | null;
  uri?: string | null;
  path?: string | null;
  source_path?: string | null;
  metadata?: Record<string, unknown> | null;
  extra_metadata?: Record<string, unknown> | null;
};

const URL_IMPORT_POLL_INTERVAL_MS = 5000;
const URL_IMPORT_MAX_POLL_ATTEMPTS = 60;

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
  const [notice, setNotice] = useState<SourceNotice | null>(null);
  const [pendingSources, setPendingSources] = useState<PendingSourceItem[]>([]);

  const { selectedDocIds, toggleSelectedDoc, setSelectedDoc, setDrawerOpen, drawerOpen, clearSelectedDocsById } = useWorkspaceStore();
  const { offline } = useSettingsStore();
  const { status, reset } = useAvailabilityStore();
  const { density, sourceDrawerDefaultOpen } = useWorkspacePreferences();
  const abortRef = useRef<AbortController | null>(null);
  const suppressAutoOpenRef = useRef(false);
  const prevDrawerOpenRef = useRef(drawerOpen);
  const mountedRef = useRef(true);
  const noticeTimerRef = useRef<number | null>(null);
  const urlImportPollsRef = useRef<Map<string, UrlImportPollState>>(new Map());

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (noticeTimerRef.current !== null) {
        window.clearTimeout(noticeTimerRef.current);
      }
      urlImportPollsRef.current.forEach((pollState) => {
        pollState.active = false;
        if (pollState.timerId !== null) {
          window.clearTimeout(pollState.timerId);
        }
      });
      urlImportPollsRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (prevDrawerOpenRef.current === true && drawerOpen === false) {
      suppressAutoOpenRef.current = true;
    }
    prevDrawerOpenRef.current = drawerOpen;
  }, [drawerOpen]);

  const isBackendOnline = status === 'online' && !offline;
  const isChecking = status === 'checking';

  const showNotice = useCallback((tone: SourceNoticeTone, message: string, durationMs = 7000) => {
    if (noticeTimerRef.current !== null) {
      window.clearTimeout(noticeTimerRef.current);
    }
    setNotice({ id: Date.now(), tone, message });
    noticeTimerRef.current = window.setTimeout(() => {
      if (mountedRef.current) {
        setNotice(null);
      }
      noticeTimerRef.current = null;
    }, durationMs);
  }, []);

  const fetchFreshSources = useCallback(async (options?: { signal?: AbortSignal; showLoading?: boolean }): Promise<SourceItem[]> => {
    if (options?.showLoading) {
      setLoading(true);
    }
    try {
      const data = await SourceService.getSources({ signal: options?.signal });
      if (mountedRef.current) {
        setSources(data);
      }
      return data;
    } finally {
      if (options?.showLoading && mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const loadSources = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    void fetchFreshSources({ signal: controller.signal, showLoading: true })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'CanceledError') return;
      });
  }, [fetchFreshSources]);

  const describeBackgroundIngestError = (err: unknown): string => {
    if (axios.isAxiosError(err) && err.code === 'ECONNABORTED') {
      return 'timeout';
    }
    const message = getErrorMessage(err, 'Failed to ingest URL');
    if (/timeout of \d+ms exceeded/i.test(message)) {
      return 'timeout';
    }
    return message;
  };

  const normalizeUrlForMatch = (value: string | null | undefined): string => {
    if (!value) return '';
    try {
      return new URL(value).href.replace(/\/$/, '').toLowerCase();
    } catch {
      return value.replace(/\/$/, '').toLowerCase();
    }
  };

  const metadataString = (metadata: Record<string, unknown> | null | undefined, key: string): string | null => {
    const value = metadata?.[key];
    return typeof value === 'string' ? value : null;
  };

  const sourceMatchesSubmittedUrl = (source: SourceItem, submittedUrl: string): boolean => {
    const normalizedSubmitted = normalizeUrlForMatch(submittedUrl);
    const expandedSource = source as SourceItemWithOptionalUrlFields;
    const candidates = [
      source.requested_url,
      source.final_url,
      source.source,
      source.source_state?.source,
      expandedSource.url,
      expandedSource.uri,
      expandedSource.path,
      expandedSource.source_path,
      metadataString(expandedSource.metadata, 'url'),
      metadataString(expandedSource.metadata, 'requested_url'),
      metadataString(expandedSource.metadata, 'final_url'),
      metadataString(expandedSource.metadata, 'source'),
      metadataString(expandedSource.metadata, 'source_path'),
      metadataString(expandedSource.extra_metadata, 'url'),
      metadataString(expandedSource.extra_metadata, 'requested_url'),
      metadataString(expandedSource.extra_metadata, 'final_url'),
      metadataString(expandedSource.extra_metadata, 'source'),
      metadataString(expandedSource.extra_metadata, 'source_path'),
    ];
    return candidates.some(
      (candidate) => normalizeUrlForMatch(candidate) === normalizedSubmitted
    );
  };

  const backendHasSubmittedUrl = (items: SourceItem[], submittedUrl: string): boolean =>
    items.some((source) => sourceMatchesSubmittedUrl(source, submittedUrl));

  const removePendingSource = useCallback((submittedUrl: string) => {
    const normalizedSubmitted = normalizeUrlForMatch(submittedUrl);
    setPendingSources((current) => current.filter((item) => item.normalizedUrl !== normalizedSubmitted));
  }, []);

  const markPendingSource = useCallback((submittedUrl: string, status: PendingSourceStatus, failureReason?: string) => {
    const normalizedSubmitted = normalizeUrlForMatch(submittedUrl);
    setPendingSources((current) =>
      current.map((item) =>
        item.normalizedUrl === normalizedSubmitted ? { ...item, status, failureReason } : item
      )
    );
  }, []);

  const upsertPendingSource = useCallback((submittedUrl: string) => {
    const normalizedSubmitted = normalizeUrlForMatch(submittedUrl);
    setPendingSources((current) => {
      const existing = current.find((item) => item.normalizedUrl === normalizedSubmitted);
      if (existing) {
        return current.map((item) =>
          item.normalizedUrl === normalizedSubmitted
            ? { ...item, url: submittedUrl, status: 'importing', failureReason: undefined }
            : item
        );
      }
      return [
        {
          id: `pending-url-${Date.now()}`,
          url: submittedUrl,
          normalizedUrl: normalizedSubmitted,
          status: 'importing',
        },
        ...current,
      ];
    });
  }, []);

  const refreshSourcesAndCheckUrl = useCallback(async (submittedUrl: string): Promise<boolean> => {
    try {
      const data = await fetchFreshSources();
      return backendHasSubmittedUrl(data, submittedUrl);
    } catch {
      return false;
    }
  }, [fetchFreshSources]);

  const stopPollingForSubmittedUrl = useCallback((submittedUrl: string) => {
    const normalizedSubmitted = normalizeUrlForMatch(submittedUrl);
    const pollState = urlImportPollsRef.current.get(normalizedSubmitted);
    if (!pollState) return;
    pollState.active = false;
    if (pollState.timerId !== null) {
      window.clearTimeout(pollState.timerId);
    }
    urlImportPollsRef.current.delete(normalizedSubmitted);
  }, []);

  const pollForSubmittedUrl = useCallback((submittedUrl: string) => {
    const normalizedSubmitted = normalizeUrlForMatch(submittedUrl);
    const existingPoll = urlImportPollsRef.current.get(normalizedSubmitted);
    if (existingPoll?.active) {
      return;
    }

    let attempts = 0;
    const pollState: UrlImportPollState = { active: true, timerId: null };
    urlImportPollsRef.current.set(normalizedSubmitted, pollState);

    const clearPollState = () => {
      pollState.active = false;
      if (pollState.timerId !== null) {
        window.clearTimeout(pollState.timerId);
      }
      if (urlImportPollsRef.current.get(normalizedSubmitted) === pollState) {
        urlImportPollsRef.current.delete(normalizedSubmitted);
      }
    };

    const poll = async () => {
      if (!pollState.active) return;
      attempts += 1;
      const found = await refreshSourcesAndCheckUrl(submittedUrl);
      if (!mountedRef.current || !pollState.active) return;
      if (found) {
        clearPollState();
        removePendingSource(submittedUrl);
        showNotice('success', 'URL imported into the knowledge base.');
        return;
      }
      if (attempts >= URL_IMPORT_MAX_POLL_ATTEMPTS) {
        clearPollState();
        markPendingSource(submittedUrl, 'still_processing');
        showNotice('warning', 'MindDock is still processing this URL or the import may have failed. Please refresh again later.', 10000);
        return;
      }
      pollState.timerId = window.setTimeout(poll, URL_IMPORT_POLL_INTERVAL_MS);
    };
    void poll();
  }, [markPendingSource, refreshSourcesAndCheckUrl, removePendingSource, showNotice]);

  const handleUrlSubmitted = useCallback((submittedUrl: string) => {
    upsertPendingSource(submittedUrl);
    showNotice('info', 'URL submitted. MindDock is importing it in the background.');
    pollForSubmittedUrl(submittedUrl);
    void SourceService.ingestUrls([submittedUrl])
      .then(async (result) => {
        if (!mountedRef.current) return;
        const freshSources = await fetchFreshSources().catch(() => []);
        if (!mountedRef.current) return;
        const failedSources = result.failed_sources || [];
        if (failedSources.length > 0) {
          const firstFailure = failedSources[0];
          stopPollingForSubmittedUrl(submittedUrl);
          markPendingSource(submittedUrl, 'failed', firstFailure?.reason || 'MindDock could not ingest this URL.');
          showNotice('warning', firstFailure?.reason || 'MindDock could not ingest this URL.', 10000);
          return;
        }
        if (backendHasSubmittedUrl(freshSources, submittedUrl)) {
          stopPollingForSubmittedUrl(submittedUrl);
          removePendingSource(submittedUrl);
          showNotice('success', 'URL imported into the knowledge base.');
        }
      })
      .catch(async (err: unknown) => {
        if (!mountedRef.current) return;
        const message = describeBackgroundIngestError(err);
        const freshSources = await fetchFreshSources().catch(() => []);
        if (!mountedRef.current) return;
        if (message === 'timeout') {
          if (backendHasSubmittedUrl(freshSources, submittedUrl)) {
            stopPollingForSubmittedUrl(submittedUrl);
            removePendingSource(submittedUrl);
            showNotice('success', 'URL imported into the knowledge base.');
            return;
          }
          return;
        }
        stopPollingForSubmittedUrl(submittedUrl);
        markPendingSource(submittedUrl, 'failed', message);
        showNotice('error', message, 10000);
      });
  }, [fetchFreshSources, markPendingSource, pollForSubmittedUrl, removePendingSource, showNotice, stopPollingForSubmittedUrl, upsertPendingSource]);

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

  const visiblePendingSources = useMemo(() => {
    return pendingSources.filter((pending) => {
      if (sources.some((source) => sourceMatchesSubmittedUrl(source, pending.url))) {
        return false;
      }
      if (filterTab !== 'All' && filterTab !== 'URL') {
        return false;
      }
      if (!searchQuery.trim()) {
        return true;
      }
      const q = searchQuery.toLowerCase();
      return pending.url.toLowerCase().includes(q) || pending.status.toLowerCase().includes(q);
    });
  }, [filterTab, pendingSources, searchQuery, sources]);

  const d = density;
  const totalSourceCount = sources.length + visiblePendingSources.length;
  const noticeStyles: Record<SourceNoticeTone, { bg: string; border: string; color: string }> = {
    info: { bg: 'var(--color-info-bg)', border: 'var(--color-info-border)', color: 'var(--color-info-text)' },
    success: { bg: 'var(--color-success-bg)', border: 'var(--color-success-border)', color: 'var(--color-success-text)' },
    warning: { bg: 'var(--color-warning-bg)', border: 'var(--color-warning-border)', color: 'var(--color-warning-text)' },
    error: { bg: 'var(--color-error-bg)', border: 'var(--color-error-border)', color: 'var(--color-error-text)' },
  };
  const pendingDetailsMessage = 'MindDock is still fetching, chunking, and indexing this URL. Details will be available after import completes.';
  const getSourceStatus = (src: SourceItem): string => src.source_state?.ingest_status || 'ready';
  const isReadySource = (src: SourceItem): boolean => getSourceStatus(src) === 'ready';
  const getUnavailableSourceMessage = (src: SourceItem): string => {
    const statusValue = getSourceStatus(src);
    if (statusValue === 'failed') {
      return src.source_state?.error_message || 'MindDock could not ingest this source. Chunks are unavailable.';
    }
    return 'MindDock is still importing this source. Chunks and retrieval selection will be available after import completes.';
  };

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
            {totalSourceCount} source{totalSourceCount !== 1 ? 's' : ''}
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

      <AddUrlDialog open={addUrlOpen} onClose={() => setAddUrlOpen(false)} onSubmit={handleUrlSubmitted} />

      {/* Search */}
      <div style={{ padding: d === 'compact' ? '8px 12px' : '10px 14px', borderBottom: '1px solid var(--color-border-subtle)', background: 'var(--color-canvas-subtle)' }}>
        {notice && (
          <div
            role="status"
            style={{
              marginBottom: '8px',
              padding: '8px 10px',
              borderRadius: 'var(--radius-md)',
              background: noticeStyles[notice.tone].bg,
              border: `1px solid ${noticeStyles[notice.tone].border}`,
              color: noticeStyles[notice.tone].color,
              fontSize: '12px',
              lineHeight: 1.4,
            }}
          >
            {notice.message}
          </div>
        )}
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

        {!loading && !isChecking && !offline && filteredSources.length === 0 && visiblePendingSources.length === 0 && (
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

        {visiblePendingSources.map(pending => {
          const isFailed = pending.status === 'failed';
          const isStillProcessing = pending.status === 'still_processing';
          const pendingLabel = isFailed ? 'Failed' : isStillProcessing ? 'Still processing' : 'Importing';
          const pendingBg = isFailed ? 'var(--color-error-bg)' : 'var(--color-warning-bg)';
          const pendingColor = isFailed ? 'var(--color-error-text)' : 'var(--color-warning-text)';
          const pendingBorder = isFailed ? 'var(--color-error-border)' : 'var(--color-warning-border)';
          const pendingMessage = isFailed
            ? pending.failureReason || 'MindDock could not ingest this URL.'
            : pendingDetailsMessage;
          return (
            <div
              key={pending.id}
              onClick={() => showNotice(isFailed ? 'error' : 'info', pendingMessage, 10000)}
              style={{
                padding: d === 'compact' ? '8px 10px' : '10px 12px',
                marginBottom: '4px',
                borderRadius: 'var(--radius-md)',
                cursor: 'default',
                background: 'var(--color-canvas-subtle)',
                border: `1px dashed ${pendingBorder}`,
                opacity: isFailed ? 0.9 : 1,
                transition: 'all var(--transition-fast)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '28px', height: '28px', borderRadius: '6px', flexShrink: 0,
                  background: isFailed ? 'var(--color-error-bg)' : '#fef9c3',
                  color: pendingColor, fontSize: '10px', fontWeight: 700,
                  marginTop: '1px',
                }}>
                  URL
                </span>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {pending.url}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        showNotice(isFailed ? 'error' : 'info', pendingMessage, 10000);
                      }}
                      title="Import in progress"
                      style={{
                        background: 'none', border: 'none',
                        cursor: 'pointer', padding: '2px 6px', borderRadius: '4px',
                        color: pendingColor,
                        fontSize: '13px', opacity: 0.8,
                        flexShrink: 0, transition: 'all var(--transition-fast)',
                      }}
                    >
                      <IconBookOpen size={14} />
                    </button>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center',
                        background: pendingBg,
                        color: pendingColor,
                        borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '10px', fontWeight: 600,
                        border: `1px solid ${pendingBorder}`,
                      }}>
                        {pendingLabel}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {filteredSources.map(src => {
          const isSelected = selectedDocIds.includes(src.doc_id);
          const kind = inferSourceKind(src.source, src.source_type);
          const isBusy = refreshingId === src.doc_id || deletingId === src.doc_id;
          const statusValue = getSourceStatus(src);
          const isReady = isReadySource(src);
          const isFailed = statusValue === 'failed';
          const canReingest = !isBusy && (isReady || isFailed);
          const unavailableMessage = getUnavailableSourceMessage(src);
          return (
            <div
              key={src.doc_id}
              onClick={() => {
                if (!isReady) {
                  showNotice(isFailed ? 'error' : 'info', unavailableMessage, 10000);
                  return;
                }
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
                cursor: isReady ? 'pointer' : 'default',
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
                        if (!isReady) {
                          showNotice(isFailed ? 'error' : 'info', unavailableMessage, 10000);
                          return;
                        }
                        setSelectedDoc(src.doc_id, src);
                        setDrawerOpen(true);
                      }}
                      title={isReady ? 'View details' : 'Chunks unavailable until import succeeds'}
                      style={{
                        background: 'none', border: 'none',
                        cursor: isReady ? 'pointer' : 'help', padding: '2px 6px', borderRadius: '4px',
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
                      <span
                        title={src.source_state?.error_message || undefined}
                        style={{
                          display: 'inline-flex', alignItems: 'center',
                          background: statusValue === 'ready' ? 'var(--color-success-bg)' : statusValue === 'failed' ? 'var(--color-error-bg)' : 'var(--color-warning-bg)',
                          color: statusValue === 'ready' ? 'var(--color-success-text)' : statusValue === 'failed' ? 'var(--color-error-text)' : 'var(--color-warning-text)',
                          borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '10px', fontWeight: 600,
                          border: `1px solid ${statusValue === 'ready' ? 'var(--color-success-border)' : statusValue === 'failed' ? 'var(--color-error-border)' : 'var(--color-warning-border)'}`,
                        }}
                      >
                        {statusValue === 'ready' ? '● ready' : statusValue === 'indexing' ? '◌ indexing...' : statusValue === 'failed' ? '✕ failed' : '○ ' + statusValue}
                      </span>
                      {(() => {
                        const tp = metadataString(src.representative_metadata, 'transcript_provider');
                        if (!tp) return null;
                        return (
                          <span style={{
                            display: 'inline-flex', alignItems: 'center',
                            background: 'var(--color-info-bg)',
                            color: 'var(--color-info-text)',
                            border: '1px solid var(--color-info-border)',
                            borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '10px', fontWeight: 600,
                          }}>
                            Transcript: {tp}
                          </span>
                        );
                      })()}
                      {metadataString(src.representative_metadata, 'has_derived_summary') === 'true' && (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center',
                          background: 'var(--color-success-bg)',
                          color: 'var(--color-success-text)',
                          border: '1px solid var(--color-success-border)',
                          borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '10px', fontWeight: 600,
                        }}>
                          Summary
                        </span>
                      )}
                      {metadataString(src.representative_metadata, 'has_derived_outline') === 'true' && (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center',
                          background: 'var(--color-success-bg)',
                          color: 'var(--color-success-text)',
                          border: '1px solid var(--color-success-border)',
                          borderRadius: 'var(--radius-full)', padding: '1px 8px', fontSize: '10px', fontWeight: 600,
                        }}>
                          Outline
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                      <button
                        onClick={(e) => handleReingest(src.doc_id, e)}
                        disabled={!canReingest}
                        title="Reingest"
                        style={{
                          background: 'none', border: 'none', cursor: canReingest ? 'pointer' : 'not-allowed',
                          padding: '6px', borderRadius: '4px', color: canReingest ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)',
                          fontSize: '12px', transition: 'color var(--transition-fast), background var(--transition-fast)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          minWidth: '24px', minHeight: '24px',
                        }}
                        onMouseOver={(e) => { if (canReingest) { e.currentTarget.style.color = 'var(--color-brand-600)'; e.currentTarget.style.background = 'var(--color-brand-50)'; } }}
                        onMouseOut={(e) => { e.currentTarget.style.color = canReingest ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)'; e.currentTarget.style.background = 'transparent'; }}
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
                  {isFailed && src.source_state?.error_message && (
                    <div style={{
                      marginTop: '6px',
                      color: 'var(--color-error-text)',
                      fontSize: '11px',
                      lineHeight: 1.4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      {src.source_state.error_message}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
