import React, { useState } from 'react';
import { AgentInput } from './agent-input';
import { AgentMessageList } from './agent-message-list';
import { AgentRunStatus } from './agent-run-status';
import { ContextBar } from './context-bar';

interface AgentPanelProps {
  onSettingsClick?: () => void;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ onSettingsClick }) => {
  const [controller, setController] = useState<AbortController | null>(null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', background: '#f4f4f5' }}>
      {/* Context Bar */}
      <ContextBar onSettingsClick={onSettingsClick} />

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
