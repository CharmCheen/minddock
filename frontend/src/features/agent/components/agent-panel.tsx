import React, { useState } from 'react';
import { AgentInput } from './agent-input';
import { AgentMessageList } from './agent-message-list';
import { AgentRunStatus } from './agent-run-status';

export const AgentPanel: React.FC = () => {
  const [controller, setController] = useState<AbortController | null>(null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', background: '#fff' }}>
      {/* Header bar */}
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
          background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
          color: '#fff',
          fontSize: '18px',
          boxShadow: '0 2px 8px rgba(59, 130, 246, 0.3)'
        }}>
          🤖
        </div>
        <div>
          <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: '#0f172a' }}>Agent Workspace</h2>
          <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Ask questions, summarize or compare documents</p>
        </div>
      </div>

      {/* Main chat view */}
      <AgentMessageList />

      {/* Footer Area with Status and Input */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <AgentRunStatus />
        <AgentInput controller={controller} setController={setController} />
      </div>
    </div>
  );
};
