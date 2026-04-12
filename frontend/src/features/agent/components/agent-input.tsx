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

  return (
    <div style={{
      padding: '16px 20px',
      borderTop: '1px solid #e2e8f0',
      background: '#fff',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px'
    }}>
      {/* Mode Switcher */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{
          display: 'flex',
          background: '#f1f5f9',
          padding: '4px',
          borderRadius: '10px',
          gap: '4px'
        }}>
          {modes.map(m => (
            <div
              key={m.id}
              onClick={() => !isRunning && setTaskType(m.id as any)}
              style={{
                padding: '8px 20px',
                fontSize: '13px',
                fontWeight: taskType === m.id ? '600' : '500',
                color: taskType === m.id ? '#1e293b' : '#64748b',
                background: taskType === m.id ? '#fff' : 'transparent',
                borderRadius: '8px',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                boxShadow: taskType === m.id ? '0 2px 4px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.2s ease'
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
        gap: '10px',
        maxWidth: '800px',
        margin: '0 auto',
        width: '100%',
        padding: '0 24px'
      }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleStart()}
          placeholder="Ask the agent anything..."
          style={{
            flex: 1,
            padding: '14px 18px',
            fontSize: '15px',
            borderRadius: '12px',
            border: '1px solid #e2e8f0',
            outline: 'none',
            transition: 'all 0.2s ease',
            boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.04)'
          }}
          onFocus={(e) => {
            e.target.style.borderColor = '#3b82f6';
            e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.1)';
          }}
          onBlur={(e) => {
            e.target.style.borderColor = '#e2e8f0';
            e.target.style.boxShadow = 'inset 0 1px 3px rgba(0,0,0,0.04)';
          }}
          disabled={isRunning}
        />
        {isRunning ? (
          <button
            onClick={handleCancel}
            style={{
              padding: '0 24px',
              cursor: 'pointer',
              background: '#ef4444',
              color: '#fff',
              border: 'none',
              borderRadius: '12px',
              fontWeight: '600',
              fontSize: '14px',
              boxShadow: '0 2px 8px rgba(239, 68, 68, 0.3)',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => e.currentTarget.style.background = '#dc2626'}
            onMouseOut={(e) => e.currentTarget.style.background = '#ef4444'}
          >
            Stop
          </button>
        ) : (
          <button
            onClick={handleStart}
            disabled={!query.trim()}
            style={{
              padding: '0 24px',
              cursor: !query.trim() ? 'not-allowed' : 'pointer',
              background: !query.trim() ? '#cbd5e1' : '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '12px',
              fontWeight: '600',
              fontSize: '14px',
              boxShadow: !query.trim() ? 'none' : '0 2px 8px rgba(59, 130, 246, 0.3)',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => {
              if (query.trim()) e.currentTarget.style.background = '#2563eb';
            }}
            onMouseOut={(e) => {
              if (query.trim()) e.currentTarget.style.background = '#3b82f6';
            }}
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
};
