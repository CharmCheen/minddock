import React from 'react';
import { useAgentStore } from '../store';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';

const PHASE_LABELS: Record<string, string> = {
  preparing: 'Preparing',
  resolving_runtime: 'Loading model',
  retrieving: 'Finding relevant sources',
  generating: 'Generating answer',
  finalizing: 'Finalizing response',
};

export const AgentRunStatus: React.FC = () => {
  const { status, events, error, runId } = useAgentStore();
  const { showWorkflowDetails, setShowWorkflowDetails, density } = useWorkspacePreferences();

  if (status === 'idle') return null;

  const currentProgress = [...events].reverse().find((event) => event.event === 'progress');
  const progressData = currentProgress?.data as { phase?: string; message?: string } | undefined;
  const progressText = progressData?.phase
    ? `${PHASE_LABELS[progressData.phase] ?? progressData.phase}: ${progressData.message ?? ''}`
    : '';

  const statusConfig: Record<string, { color: string; bg: string; border: string; label: string }> = {
    running: {
      color: 'var(--color-brand-600)',
      bg: 'var(--color-info-bg)',
      border: 'var(--color-info-border)',
      label: 'Running',
    },
    completed: {
      color: 'var(--color-success-text)',
      bg: 'var(--color-success-bg)',
      border: 'var(--color-success-border)',
      label: 'Completed',
    },
    failed: {
      color: 'var(--color-error-text)',
      bg: 'var(--color-error-bg)',
      border: 'var(--color-error-border)',
      label: 'Failed',
    },
    cancelling: {
      color: '#b45309',
      bg: 'var(--color-warning-bg)',
      border: 'var(--color-warning-border)',
      label: 'Cancelling',
    },
    cancelled: {
      color: '#b45309',
      bg: 'var(--color-warning-bg)',
      border: 'var(--color-warning-border)',
      label: 'Cancelled',
    },
  };

  const cfg = statusConfig[status] || statusConfig.running;
  const d = density;

  return (
    <div style={{ padding: '0 16px', fontSize: '12px', background: 'transparent', marginTop: '8px', marginBottom: '4px' }}>
      <div
        style={{
          padding: d === 'compact' ? '8px 14px' : '10px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: cfg.bg,
          border: `1px solid ${cfg.border}`,
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
          {/* Status dot */}
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: cfg.color,
            flexShrink: 0,
            animation: status === 'running' ? 'pulse 2s ease-in-out infinite' : undefined,
          }} />
          <span
            style={{
              fontWeight: 700,
              color: cfg.color,
              textTransform: 'uppercase',
              fontSize: '11px',
              letterSpacing: '0.04em',
              flexShrink: 0,
            }}
          >
            {cfg.label}
          </span>
          {status === 'running' && progressText && (
            <span style={{ color: 'var(--color-text-secondary)', fontSize: '12px', paddingLeft: '10px', borderLeft: '1px solid var(--color-border-subtle)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {progressText}
            </span>
          )}
          {status === 'failed' && error && (
            <span style={{ color: 'var(--color-error-text)', fontSize: '12px', paddingLeft: '10px', borderLeft: '1px solid var(--color-error-border)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {error}
            </span>
          )}
          {(status === 'cancelling' || status === 'cancelled') && error && (
            <span style={{ color: '#b45309', fontSize: '12px', paddingLeft: '10px', borderLeft: '1px solid var(--color-warning-border)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {error}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
          {runId && showWorkflowDetails && (
            <span style={{
              color: 'var(--color-text-tertiary)',
              fontSize: '10px',
              background: 'var(--color-surface)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              border: '1px solid var(--color-border-subtle)',
              fontFamily: 'var(--font-mono)',
            }}>
              {runId.substring(0, 8)}
            </span>
          )}
          {events.length > 0 && (
            <button
              type="button"
              onClick={() => setShowWorkflowDetails(!showWorkflowDetails)}
              style={{
                fontSize: '11px',
                color: 'var(--color-text-tertiary)',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                cursor: 'pointer',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 500,
                transition: 'all var(--transition-fast)',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.color = 'var(--color-text-secondary)';
                e.currentTarget.style.borderColor = 'var(--color-border-default)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.color = 'var(--color-text-tertiary)';
                e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
              }}
            >
              {showWorkflowDetails ? 'Hide details' : 'Show details'}
            </button>
          )}
        </div>
      </div>

      {showWorkflowDetails && events.length > 0 && (
        <div style={{
          maxHeight: '200px',
          overflowY: 'auto',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-subtle)',
          borderTop: 'none',
          borderRadius: '0 0 var(--radius-md) var(--radius-md)',
          padding: d === 'compact' ? '10px 14px' : '12px 16px',
          marginTop: '-4px',
          paddingTop: '14px',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', fontWeight: 600, marginBottom: '8px', letterSpacing: '0.02em' }}>
            What happened ({events.length} step{events.length === 1 ? '' : 's'})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {events.slice().reverse().slice(0, 20).map((event, index) => (
              <div
                key={`${event.event}-${index}`}
                style={{
                  fontSize: '12px',
                  color: 'var(--color-text-secondary)',
                  padding: '6px 10px',
                  background: 'var(--color-canvas-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: event.event === 'progress' ? 'var(--color-brand-500)' : event.event === 'artifact' ? 'var(--color-success-text)' : event.event === 'failed' ? 'var(--color-error-text)' : 'var(--color-text-tertiary)',
                  flexShrink: 0,
                }} />
                <span style={{ fontWeight: 500 }}>
                  {event.event === 'progress'
                    ? (PHASE_LABELS[(event.data as { phase?: string })?.phase || ''] ?? (event.data as { phase?: string })?.phase)
                    : event.event === 'run_started'
                    ? 'Started'
                    : event.event === 'artifact'
                    ? 'Answer ready'
                    : event.event === 'completed'
                    ? 'Done'
                    : event.event === 'failed'
                    ? 'Failed'
                    : event.event}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
