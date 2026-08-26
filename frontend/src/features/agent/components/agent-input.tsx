import React, { useState, useEffect } from 'react';
import { useAgentStore } from '../store';
import { useAvailabilityStore } from '../../app/store/availability';
import { useWorkspaceStore } from '../../workspace/store';
import { buildUserPreferenceProfile, useWorkspacePreferences } from '../../settings/workspace-preferences';
import { ExamplePrompts } from './example-prompts';
import { ExecutionService } from '../../../lib/api/services/execution';
import { ClientArtifactPayload, ClientEvent } from '../../../core/types/api';
import { cancelActiveRun } from '../cancellation';
import { IconFileText } from '../../../components/ui/icons';

export const AgentInput: React.FC<{
  controller: AbortController | null;
  setController: (ctrl: AbortController | null) => void;
}> = ({ controller, setController }) => {
  const [query, setQuery] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Academic metadata filters (PRD FR-3 UI): author + year range only.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filterAuthor, setFilterAuthor] = useState('');
  const [filterYearFrom, setFilterYearFrom] = useState('');
  const [filterYearTo, setFilterYearTo] = useState('');
  const { status, taskType, runId, setTaskType, turns, prepareRun, startRun, appendEvent, appendArtifact, finishRun, failRun, requestCancel, markCancelled, reset } = useAgentStore();
  const { status: backendStatus } = useAvailabilityStore();
  const { selectedDocIds, selectedDocDetails, clearSelectedDocs } = useWorkspaceStore();
  const preferences = useWorkspacePreferences();
  const {
    defaultTaskType,
    defaultTopK,
    defaultCitationPolicy,
    defaultAnswerStyle,
    defaultSummarizeMode,
    density,
  } = preferences;

  // Sync default task type from preferences when idle
  useEffect(() => {
    if (status === 'idle' && !query && turns.length === 0) {
      setTaskType(defaultTaskType);
    }
  }, [defaultTaskType, status, query, turns.length, setTaskType]);

  // Abort any in-progress stream on unmount / HMR
  useEffect(() => {
    return () => {
      if (controller) {
        controller.abort();
      }
    };
  }, [controller]);

  const handleStart = () => {
    if (!query.trim()) return;
    if (backendStatus === 'offline' || backendStatus === 'checking') {
      failRun('Backend is not available. Please wait or retry.');
      return;
    }

    const sources = selectedDocDetails.map((detail) => detail.source).filter(Boolean);
    const authors = filterAuthor.trim()
      ? filterAuthor.split(/[,;，；]/).map((a) => a.trim()).filter(Boolean)
      : undefined;
    const yearFrom = filterYearFrom.trim() ? Number(filterYearFrom) : undefined;
    const yearTo = filterYearTo.trim() ? Number(filterYearTo) : undefined;

    reset();
    prepareRun(query, { selectedSources: sources });

    const ctrl = ExecutionService.executeStream(
      {
        query,
        task_type: taskType,
        sources,
        top_k: defaultTopK,
        citation_policy: defaultCitationPolicy,
        summarize_mode: taskType === 'summarize' ? defaultSummarizeMode : undefined,
        answer_style: defaultAnswerStyle,
        preference_profile: buildUserPreferenceProfile(preferences),
        authors,
        year_from: Number.isFinite(yearFrom) ? yearFrom : undefined,
        year_to: Number.isFinite(yearTo) ? yearTo : undefined,
      },
      {
        onEvent: (event: ClientEvent) => {
          appendEvent(event);
          if (event.event === 'run_started') {
            startRun(event.run_id!, query);
          } else if (event.event === 'progress') {
            // Phase info is stored via appendEvent above; AgentRunStatus reads it for display
          } else if (event.event === 'artifact') {
            const payload = event.data as ClientArtifactPayload;
            if (payload && payload.artifact) {
              appendArtifact(payload.artifact);
            }
          } else if (event.event === 'completed') {
            finishRun();
          } else if (event.event === 'failed') {
            const data = event.data as Record<string, unknown>;
            const raw = (data.detail || data.error || data.message || 'Stream failed') as string;
            const friendly = raw.includes('RuntimeInvocationError')
              ? 'Runtime 调用失败，请检查 base_url、api_key 或模型名称。'
              : raw;
            failRun(friendly);
          }
        },
        onError: (err, isNetworkError) => {
          if (isNetworkError) {
            failRun('Backend unreachable. Retrying connection…');
          } else {
            failRun(err.message);
          }
          setController(null);
        },
        onDone: () => {
          setController(null);
          setQuery('');
        }
      }
    );

    setController(ctrl);
  };

  const handleCancel = () => {
    cancelActiveRun({
      runId,
      controller,
      cancelRun: ExecutionService.cancelRun,
      requestCancel,
      markCancelled,
      failRun,
      setController,
    });
  };

  const isRunning = status === 'running';
  const isCancelling = status === 'cancelling';
  const d = density;

  const modes = [
    { id: 'auto', label: 'Auto' },
    { id: 'chat', label: 'Chat' },
    { id: 'summarize', label: 'Summarize' },
    { id: 'compare', label: 'Compare' }
  ];

  const MODE_INFO: Record<string, { title: string; subtitle: string; placeholder: string }> = {
    auto: {
      title: 'Auto mode',
      subtitle: 'The system will automatically detect the best task type for your query.',
      placeholder: 'Ask anything - Auto mode will choose the task type...',
    },
    chat: {
      title: 'Ask with evidence',
      subtitle: 'Question-answering over indexed sources with verifiable citations.',
      placeholder: 'Ask a specific question about your knowledge base...',
    },
    summarize: {
      title: 'Summarize sources',
      subtitle: 'Condense selected documents into key points and grounded takeaways.',
      placeholder: 'Summarize the selected source, topic, or set of documents...',
    },
    compare: {
      title: 'Compare sources',
      subtitle: 'Find shared claims, differences, conflicts, and a grounded conclusion.',
      placeholder: 'Compare two or more sources on...',
    },
  };

  const currentModeInfo = MODE_INFO[taskType] || MODE_INFO.auto;

  const getPlaceholder = () => currentModeInfo.placeholder || 'Ask MindDock anything...';

  const getButtonLabel = () => {
    if (isCancelling) return 'Cancelling';
    if (isRunning) return 'Stop';
    return taskType === 'chat' ? 'Send' : taskType === 'summarize' ? 'Summarize' : taskType === 'compare' ? 'Compare' : 'Send';
  };

  return (
    <div style={{
      padding: d === 'compact' ? '10px 16px 12px' : '14px 20px 16px',
      borderTop: '1px solid var(--color-border-subtle)',
      background: 'var(--color-surface)',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    }}>
      {/* Mode Switcher */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{
          display: 'flex',
          background: 'var(--color-canvas)',
          padding: '3px',
          borderRadius: 'var(--radius-md)',
          gap: '2px',
          border: '1px solid var(--color-border-subtle)',
        }}>
          {modes.map(m => (
            <div
              key={m.id}
              data-testid={`mode-${m.id}`}
              onClick={() => !isRunning && !isCancelling && setTaskType(m.id as any)}
              style={{
                padding: d === 'compact' ? '5px 14px' : '6px 16px',
                fontSize: '12px',
                fontWeight: taskType === m.id ? '700' : '500',
                color: taskType === m.id ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)',
                background: taskType === m.id ? 'var(--color-surface)' : 'transparent',
                borderRadius: '8px',
                cursor: isRunning || isCancelling ? 'not-allowed' : 'pointer',
                boxShadow: taskType === m.id ? 'var(--shadow-sm)' : 'none',
                transition: 'all var(--transition-fast)',
                userSelect: 'none',
              }}
            >
              {m.label}
            </div>
          ))}
        </div>
      </div>

      {/* Academic metadata filters (PRD FR-3 UI): author + year range only */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <button
          type="button"
          data-testid="filters-toggle"
          onClick={() => setFiltersOpen(!filtersOpen)}
          style={{
            fontSize: '11px',
            color: filtersOpen || filterAuthor || filterYearFrom || filterYearTo
              ? 'var(--color-brand-600)'
              : 'var(--color-text-tertiary)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '2px 8px',
            fontWeight: 600,
          }}
        >
          {filtersOpen ? '▾ Filters' : '▸ Filters'}
          {(filterAuthor || filterYearFrom || filterYearTo) ? ' · active' : ''}
        </button>
      </div>
      {filtersOpen && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          flexWrap: 'wrap',
          padding: '6px 12px',
          background: 'var(--color-canvas)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-md)',
        }}>
          <label style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', fontWeight: 600 }}>
            Author
            <input
              data-testid="filter-author"
              value={filterAuthor}
              onChange={(e) => setFilterAuthor(e.target.value)}
              placeholder="e.g. Wang Rui"
              style={{
                marginLeft: '6px',
                fontSize: '12px',
                padding: '4px 8px',
                width: '160px',
                border: '1px solid var(--color-border-default)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--color-surface)',
                color: 'var(--color-text-primary)',
              }}
            />
          </label>
          <label style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', fontWeight: 600 }}>
            Year from
            <input
              data-testid="filter-year-from"
              type="number"
              min={1900}
              max={2100}
              value={filterYearFrom}
              onChange={(e) => setFilterYearFrom(e.target.value)}
              placeholder="2019"
              style={{
                marginLeft: '6px',
                fontSize: '12px',
                padding: '4px 8px',
                width: '72px',
                border: '1px solid var(--color-border-default)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--color-surface)',
                color: 'var(--color-text-primary)',
              }}
            />
          </label>
          <label style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', fontWeight: 600 }}>
            Year to
            <input
              data-testid="filter-year-to"
              type="number"
              min={1900}
              max={2100}
              value={filterYearTo}
              onChange={(e) => setFilterYearTo(e.target.value)}
              placeholder="2026"
              style={{
                marginLeft: '6px',
                fontSize: '12px',
                padding: '4px 8px',
                width: '72px',
                border: '1px solid var(--color-border-default)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--color-surface)',
                color: 'var(--color-text-primary)',
              }}
            />
          </label>
        </div>
      )}

      {!isRunning && turns.length === 0 && (
        <div style={{ textAlign: 'center', padding: '0 16px' }}>
          <div style={{
            fontSize: '15px',
            fontWeight: 600,
            color: 'var(--color-text-primary)',
            marginBottom: '4px',
          }}>
            {currentModeInfo.title}
          </div>
          <div style={{
            fontSize: '12px',
            color: 'var(--color-text-tertiary)',
            lineHeight: 1.5,
            maxWidth: '420px',
            margin: '0 auto',
          }}>
            {currentModeInfo.subtitle}
          </div>
        </div>
      )}

      {!isRunning && turns.length === 0 && (
        <ExamplePrompts taskType={taskType} onSelect={(text) => setQuery(text)} />
      )}

      {selectedDocIds.length > 0 && (
        <div style={{
          maxWidth: '760px',
          margin: '0 auto',
          width: '100%',
          padding: '0 16px',
          boxSizing: 'border-box',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            padding: '8px 14px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-info-bg)',
            border: '1px solid var(--color-info-border)',
          }}>
            <span style={{
              fontSize: '12px',
              color: 'var(--color-info-text)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {selectedDocIds.length === 1
                ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}><IconFileText size={12} /> {selectedDocDetails[0]?.source || ''}</span>
                : <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}><IconFileText size={12} /> {selectedDocIds.length} selected</span>}
            </span>
            <button
              type="button"
              onClick={clearSelectedDocs}
              title="Clear source scope"
              style={{
                border: 'none',
                background: 'transparent',
                color: 'var(--color-info-text)',
                cursor: 'pointer',
                fontSize: '14px',
                lineHeight: 1,
                padding: '2px 6px',
                borderRadius: '4px',
                flexShrink: 0,
                transition: 'background var(--transition-fast)',
              }}
              onMouseOver={(e) => { e.currentTarget.style.background = 'rgba(59, 130, 246, 0.1)'; }}
              onMouseOut={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              ×
            </button>
          </div>
        </div>
      )}

      <div style={{
        display: 'flex',
        gap: '10px',
        maxWidth: '760px',
        margin: '0 auto',
        width: '100%',
        padding: '0 16px',
      }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isRunning && handleStart()}
          placeholder={getPlaceholder()}
          data-testid="agent-input"
          style={{
            flex: 1,
            padding: d === 'compact' ? '9px 14px' : '11px 16px',
            fontSize: '14px',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--color-border-subtle)',
            outline: 'none',
            transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
            boxShadow: 'var(--shadow-inset)',
            background: 'var(--color-canvas-subtle)',
            color: 'var(--color-text-primary)',
          }}
          onFocus={(e) => {
            e.target.style.borderColor = 'var(--color-brand-200)';
            e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.1)';
          }}
          onBlur={(e) => {
            e.target.style.borderColor = 'var(--color-border-subtle)';
            e.target.style.boxShadow = 'var(--shadow-inset)';
          }}
          disabled={isRunning}
        />
        {isRunning || isCancelling ? (
          <button
            data-testid="agent-stop"
            onClick={handleCancel}
            disabled={isCancelling}
            style={{
              padding: '0 20px',
              cursor: isCancelling ? 'not-allowed' : 'pointer',
              background: 'var(--color-error-bg)',
              color: 'var(--color-error-text)',
              border: '1px solid var(--color-error-border)',
              borderRadius: 'var(--radius-lg)',
              fontWeight: '600',
              fontSize: '13px',
              transition: 'all var(--transition-fast)',
            }}
            onMouseOver={(e) => {
              if (!isCancelling) {
                e.currentTarget.style.background = '#fecaca';
              }
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'var(--color-error-bg)';
            }}
          >
            {getButtonLabel()}
          </button>
        ) : (
          <button
            data-testid="agent-submit"
            onClick={handleStart}
            disabled={!query.trim()}
            style={{
              padding: '0 20px',
              cursor: !query.trim() ? 'not-allowed' : 'pointer',
              background: !query.trim() ? 'var(--color-canvas)' : 'var(--color-brand-600)',
              color: !query.trim() ? 'var(--color-text-tertiary)' : '#fff',
              border: !query.trim() ? '1px solid var(--color-border-subtle)' : '1px solid var(--color-brand-600)',
              borderRadius: 'var(--radius-lg)',
              fontWeight: '600',
              fontSize: '13px',
              boxShadow: !query.trim() ? 'none' : 'var(--shadow-md)',
              transition: 'all var(--transition-fast)',
            }}
            onMouseOver={(e) => {
              if (query.trim()) {
                e.currentTarget.style.background = 'var(--color-brand-900)';
                e.currentTarget.style.borderColor = 'var(--color-brand-900)';
              }
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'var(--color-brand-600)';
              e.currentTarget.style.borderColor = 'var(--color-brand-600)';
            }}
          >
            {getButtonLabel()}
          </button>
        )}
      </div>
    </div>
  );
};
