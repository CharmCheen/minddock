import React, { useState } from 'react';
import { useAgentStore } from '../store';

export const AgentRunStatus: React.FC = () => {
  const { status, events, error, runId } = useAgentStore();
  const [showDetails, setShowDetails] = useState(false);

  if (status === 'idle') return null;

  const currentProgress = [...events].reverse().find(e => e.event === 'progress');
  const progressData = currentProgress?.data as any;
  const progressText = progressData?.phase
    ? `${progressData.phase}: ${progressData.message}`
    : '';

  const getStatusColor = () => {
    switch (status) {
      case 'running': return '#3b82f6';
      case 'completed': return '#10b981';
      case 'failed': return '#ef4444';
      default: return '#64748b';
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'running': return '⏳';
      case 'completed': return '✅';
      case 'failed': return '❌';
      default: return '📋';
    }
  };

  return (
    <div style={{
      padding: '0',
      fontSize: '12px',
      background: '#fff',
      borderBottom: '1px solid #e2e8f0'
    }}>
      {/* Main Status Bar */}
      <div style={{
        padding: '10px 16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: status === 'running' ? '#f8fafc' : status === 'failed' ? '#fef2f2' : status === 'completed' ? '#f0fdf4' : '#f8fafc'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '14px' }}>{getStatusIcon()}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{
              fontWeight: '600',
              color: getStatusColor(),
              textTransform: 'uppercase',
              fontSize: '11px',
              letterSpacing: '0.03em'
            }}>
              {status}
            </span>
            {status === 'running' && progressText && (
              <span style={{ color: '#64748b', marginLeft: '4px' }}>{progressText}</span>
            )}
            {status === 'failed' && error && (
              <span style={{ color: '#ef4444', marginLeft: '4px' }}>{error}</span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {runId && (
            <span style={{ color: '#94a3b8' }}>
              Run: <span style={{ fontFamily: 'monospace' }}>{runId.substring(0, 8)}</span>
            </span>
          )}
          {events.length > 0 && (
            <button
              onClick={() => setShowDetails(!showDetails)}
              style={{
                fontSize: '11px',
                color: '#64748b',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '4px 8px',
                borderRadius: '4px',
                transition: 'all 0.2s'
              }}
              onMouseOver={(e) => e.currentTarget.style.background = '#f1f5f9'}
              onMouseOut={(e) => e.currentTarget.style.background = 'none'}
            >
              {showDetails ? '▲ Hide Details' : '▼ Show Details'}
            </button>
          )}
        </div>
      </div>

      {/* Collapsible Events Detail */}
      {showDetails && events.length > 0 && (
        <div style={{
          maxHeight: '200px',
          overflowY: 'auto',
          background: '#f8fafc',
          borderTop: '1px solid #e2e8f0',
          padding: '12px 16px'
        }}>
          <div style={{
            fontSize: '11px',
            color: '#64748b',
            fontWeight: '600',
            marginBottom: '8px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em'
          }}>
            Event Log ({events.length} events)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {events.slice().reverse().slice(0, 20).map((evt, idx) => (
              <div key={idx} style={{
                fontSize: '11px',
                fontFamily: 'monospace',
                color: '#475569',
                padding: '4px 8px',
                background: '#fff',
                borderRadius: '4px',
                border: '1px solid #e2e8f0'
              }}>
                <span style={{ color: '#3b82f6', fontWeight: '500' }}>{evt.event}</span>
                {evt.event === 'progress' && (
                  <span style={{ color: '#64748b', marginLeft: '8px' }}>
                    {(evt.data as any)?.phase} - {(evt.data as any)?.message}
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
