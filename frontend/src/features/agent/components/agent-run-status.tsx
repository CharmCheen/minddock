import React, { useState } from 'react';
import { useAgentStore } from '../store';

const PHASE_LABELS: Record<string, string> = {
  preparing: 'Preparing',
  resolving_runtime: 'Resolving runtime',
  retrieving: 'Retrieving sources',
  generating: 'Generating answer',
  finalizing: 'Finalizing output',
};

export const AgentRunStatus: React.FC = () => {
  const { status, events, error, runId } = useAgentStore();
  const [showDetails, setShowDetails] = useState(false);

  if (status === 'idle') return null;

  const currentProgress = [...events].reverse().find((event) => event.event === 'progress');
  const progressData = currentProgress?.data as { phase?: string; message?: string } | undefined;
  const progressText = progressData?.phase
    ? `${PHASE_LABELS[progressData.phase] ?? progressData.phase}: ${progressData.message ?? ''}`
    : '';

  const statusColor = status === 'running' ? '#3b82f6' : status === 'completed' ? '#10b981' : status === 'failed' ? '#ef4444' : status === 'cancelling' || status === 'cancelled' ? '#f59e0b' : '#64748b';
  const statusLabel = status === 'running' ? 'Running' : status === 'completed' ? 'Completed' : status === 'failed' ? 'Failed' : status === 'cancelling' ? 'Cancelling' : status === 'cancelled' ? 'Cancelled' : status;

  return (
    <div style={{ padding: 0, fontSize: '12px', background: '#fff', borderBottom: '1px solid #e2e8f0' }}>
      <div
        style={{
          padding: '10px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: status === 'running' ? '#eff6ff' : status === 'failed' ? '#fef2f2' : status === 'completed' ? '#f0fdf4' : status === 'cancelling' || status === 'cancelled' ? '#fffbeb' : '#f8fafc',
          borderLeft: `3px solid ${statusColor}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              fontWeight: 700,
              color: statusColor,
              textTransform: 'uppercase',
              fontSize: '11px',
              letterSpacing: '0.04em',
            }}
          >
            {statusLabel}
          </span>
          {status === 'running' && progressText && (
            <span style={{ color: '#64748b', fontSize: '12px', paddingLeft: '8px', borderLeft: '1px solid #e2e8f0' }}>
              {progressText}
            </span>
          )}
          {status === 'failed' && error && (
            <span style={{ color: '#ef4444', fontSize: '12px', paddingLeft: '8px', borderLeft: '1px solid #fee2e2' }}>
              {error}
            </span>
          )}
          {(status === 'cancelling' || status === 'cancelled') && error && (
            <span style={{ color: '#92400e', fontSize: '12px', paddingLeft: '8px', borderLeft: '1px solid #fde68a' }}>
              {error}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {runId && (
            <span style={{ color: '#94a3b8', fontSize: '11px', fontFamily: 'monospace', background: '#f8fafc', padding: '2px 8px', borderRadius: '4px' }}>
              Run: {runId.substring(0, 8)}
            </span>
          )}
          {events.length > 0 && (
            <button
              type="button"
              onClick={() => setShowDetails(!showDetails)}
              style={{
                fontSize: '11px',
                color: '#64748b',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '4px 8px',
                borderRadius: '4px',
              }}
            >
              {showDetails ? 'Hide Events' : 'Show Events'}
            </button>
          )}
        </div>
      </div>

      {showDetails && events.length > 0 && (
        <div style={{ maxHeight: '200px', overflowY: 'auto', background: '#f8fafc', borderTop: '1px solid #e2e8f0', padding: '12px 16px' }}>
          <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Event Log ({events.length} events)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {events.slice().reverse().slice(0, 20).map((event, index) => (
              <div
                key={`${event.event}-${index}`}
                style={{
                  fontSize: '11px',
                  fontFamily: 'monospace',
                  color: '#475569',
                  padding: '4px 8px',
                  background: '#fff',
                  borderRadius: '4px',
                  border: '1px solid #e2e8f0',
                }}
              >
                <span style={{ color: '#3b82f6', fontWeight: 500 }}>{event.event}</span>
                {event.event === 'progress' && (
                  <span style={{ color: '#64748b', marginLeft: '8px' }}>
                    {PHASE_LABELS[(event.data as { phase?: string })?.phase || ''] ?? (event.data as { phase?: string })?.phase}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
