import React, { useState, useEffect } from 'react';
import { useAgentStore } from '../store';
import { useAvailabilityStore } from '../../app/store/availability';
import { useWorkspaceStore } from '../../workspace/store';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';
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
  const { status, taskType, runId, setTaskType, turns, prepareRun, startRun, appendEvent, appendArtifact, finishRun, failRun, requestCancel, markCancelled, reset } = useAgentStore();
  const { status: backendStatus } = useAvailabilityStore();
  const { selectedDocIds, selectedDocDetails, clearSelectedDocs } = useWorkspaceStore();
  const { defaultTaskType, defaultTopK, defaultCitationPolicy, defaultSummarizeMode, density } = useWorkspacePreferences();

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

    reset();
    prepareRun(query, { selectedSources: sources });

    const ctrl = ExecutionService.executeStream(
      { query, task_type: taskType, sources, top_k: defaultTopK, citation_policy: defaultCitationPolicy, summarize_mode: taskType === 'summarize' ? defaultSummarizeMode : undefined },
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
            const data = event.data as any;
            failRun(data.error || data.message || 'Stream failed');
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
    { id: 'chat', label: 'Chat' },
    { id: 'summarize', label: 'Summarize' },
    { id: 'compare', label: 'Compare' }
  ];

  const PLACEHOLDERS: Record<string, string> = {
    chat: 'Ask a question about your knowledge base...',
    summarize: 'What would you like to summarize?',
    compare: 'Compare perspectives across your sources...',
  };

  const getPlaceholder = () => PLACEHOLDERS[taskType] || 'Ask the agent anything...';

  const getButtonLabel = () => {
    if (isCancelling) return 'Cancelling';
    if (isRunning) return 'Stop';
    return taskType === 'chat' ? 'Send' : taskType === 'summarize' ? 'Summarize' : 'Compare';
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
