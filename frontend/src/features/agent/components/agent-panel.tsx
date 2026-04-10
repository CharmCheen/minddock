import React, { useState } from 'react';
import { AgentInput } from './agent-input';
import { AgentMessageList } from './agent-message-list';
import { AgentRunStatus } from './agent-run-status';

export const AgentPanel: React.FC = () => {
  const [controller, setController] = useState<AbortController | null>(null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', background: '#fff' }}>
      {/* Header bar */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #e2e8f0', background: '#fff' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600', color: '#0f172a' }}>Agent Workspace</h2>
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
