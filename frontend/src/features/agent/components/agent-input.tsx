import React, { useState } from 'react';
import { useAgentStore } from '../store';
import { ExamplePrompts } from './example-prompts';
import { ExecutionService } from '../../../lib/api/services/execution';
import { ClientArtifactPayload, ClientEvent } from '../../../core/types/api';

export const AgentInput: React.FC<{
  controller: AbortController | null;
  setController: (ctrl: AbortController | null) => void;
}> = ({ controller, setController }) => {
  const [query, setQuery] = useState('');
  const { status, taskType, setTaskType, artifacts, startRun, appendEvent, appendArtifact, finishRun, failRun, reset } = useAgentStore();

  const handleStart = () => {
    if (!query.trim()) return;
    
    reset();
    
    const ctrl = ExecutionService.executeStream(
      { query, task_type: taskType },
      {
        onEvent: (event: ClientEvent) => {
          appendEvent(event);
          if (event.event === 'run_started') {
            // run_id is at top level of ClientEventResponseItem, not in payload
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
        onError: (err) => {
          failRun(err.message);
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
    if (controller) {
      controller.abort();
      setController(null);
      failRun('Cancelled by user');
    }
  };

  const isRunning = status === 'running';

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
    if (isRunning) return 'Stop';
    return taskType === 'chat' ? 'Send' : taskType === 'summarize' ? 'Summarize' : 'Compare';
  };

  return (
    <div style={{
      padding: '14px 20px 16px',
      borderTop: '1px solid #e2e8f0',
      background: '#fff',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px'
    }}>
      {/* Mode Switcher */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{
          display: 'flex',
          background: '#f1f5f9',
          padding: '3px',
          borderRadius: '8px',
          gap: '2px'
        }}>
          {modes.map(m => (
            <div
              key={m.id}
              data-testid={`mode-${m.id}`}
              onClick={() => !isRunning && setTaskType(m.id as any)}
              style={{
                padding: '6px 16px',
                fontSize: '12px',
                fontWeight: taskType === m.id ? '600' : '500',
                color: taskType === m.id ? '#1e293b' : '#64748b',
                background: taskType === m.id ? '#fff' : 'transparent',
                borderRadius: '6px',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                boxShadow: taskType === m.id ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.15s ease'
              }}
            >
              {m.label}
            </div>
          ))}
        </div>
      </div>

      {!isRunning && artifacts.length === 0 && (
        <ExamplePrompts taskType={taskType} onSelect={(text) => setQuery(text)} />
      )}

      <div style={{
        display: 'flex',
        gap: '8px',
        maxWidth: '760px',
        margin: '0 auto',
        width: '100%',
        padding: '0 16px'
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
            padding: '11px 16px',
            fontSize: '14px',
            borderRadius: '10px',
            border: '1px solid #e2e8f0',
            outline: 'none',
            transition: 'border-color 0.2s, box-shadow 0.2s',
            boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.04)'
          }}
          onFocus={(e) => {
            e.target.style.borderColor = '#3b82f6';
            e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.1)';
          }}
          onBlur={(e) => {
            e.target.style.borderColor = '#e2e8f0';
            e.target.style.boxShadow = 'inset 0 1px 2px rgba(0,0,0,0.04)';
          }}
          disabled={isRunning}
        />
        {isRunning ? (
          <button
            data-testid="agent-stop"
            onClick={handleCancel}
            style={{
              padding: '0 20px',
              cursor: 'pointer',
              background: '#ef4444',
              color: '#fff',
              border: 'none',
              borderRadius: '10px',
              fontWeight: '600',
              fontSize: '13px',
              boxShadow: '0 2px 6px rgba(239, 68, 68, 0.25)',
              transition: 'background 0.15s'
            }}
            onMouseOver={e => e.currentTarget.style.background = '#dc2626'}
            onMouseOut={e => e.currentTarget.style.background = '#ef4444'}
          >
            Stop
          </button>
        ) : (
          <button
            data-testid="agent-submit"
            onClick={handleStart}
            disabled={!query.trim()}
            style={{
              padding: '0 20px',
              cursor: !query.trim() ? 'not-allowed' : 'pointer',
              background: !query.trim() ? '#e2e8f0' : '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '10px',
              fontWeight: '600',
              fontSize: '13px',
              boxShadow: !query.trim() ? 'none' : '0 2px 6px rgba(59, 130, 246, 0.25)',
              transition: 'background 0.15s, box-shadow 0.15s'
            }}
            onMouseOver={e => {
              if (query.trim()) e.currentTarget.style.background = '#2563eb';
            }}
            onMouseOut={e => {
              if (query.trim()) e.currentTarget.style.background = '#3b82f6';
            }}
          >
            {getButtonLabel()}
          </button>
        )}
      </div>
    </div>
  );
};
