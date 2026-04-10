import React from 'react';
import { useAgentStore } from '../store';

export const AgentRunStatus: React.FC = () => {
  const { status, events, error, runId } = useAgentStore();

  if (status === 'idle') return null;

  const currentProgress = [...events].reverse().find(e => e.event === 'progress');
  const progressData = currentProgress?.data as any;
  const progressText = progressData?.phase 
    ? `${progressData.phase}: ${progressData.message}` 
    : '';

  return (
    <div style={{ padding: '8px 16px', fontSize: '12px', color: '#64748b', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between' }}>
      <div>
        <span style={{ fontWeight: '600', color: status === 'failed' ? '#ef4444' : status === 'running' ? '#3b82f6' : '#10b981', textTransform: 'uppercase' }}>
          {status}
        </span>
        {status === 'running' && progressText && <span style={{ marginLeft: '12px' }}>{progressText}</span>}
        {status === 'failed' && error && <span style={{ marginLeft: '12px', color: '#ef4444' }}>{error}</span>}
      </div>
      <div>
        {runId && <span>Run: {runId.substring(0, 8)}...</span>}
      </div>
    </div>
  );
};
