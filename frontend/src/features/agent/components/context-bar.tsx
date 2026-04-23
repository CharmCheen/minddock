import React, { useEffect } from 'react';
import { useAgentStore } from '../store';
import { useWorkspaceStore } from '../../workspace/store';
import { useSettingsStore } from '../../settings/store';
import { deriveRuntimeStatus } from '../../settings/runtime-status';

const MODE_LABELS: Record<string, string> = {
  chat: 'Chat',
  summarize: 'Summarize',
  compare: 'Compare',
};

const MODE_COLORS: Record<string, string> = {
  chat: '#3b82f6',
  summarize: '#10b981',
  compare: '#8b5cf6',
};

interface ContextBarProps {
  onSettingsClick?: () => void;
}

export const ContextBar: React.FC<ContextBarProps> = ({ onSettingsClick }) => {
  const { taskType } = useAgentStore();
  const { selectedDocId, selectedDocDetail } = useWorkspaceStore();
  const { config, loadConfig, offline, loading } = useSettingsStore();

  useEffect(() => {
    if (offline) return;
    if (!config && !loading) {
      void loadConfig();
    }
  }, [config, offline, loadConfig, loading]);

  const modeColor = MODE_COLORS[taskType] || '#64748b';
  const modeLabel = MODE_LABELS[taskType] || taskType;
  const runtimeState = deriveRuntimeStatus(config);
  const effectiveRuntime = config?.effective_runtime;
  const runtimeLabel = effectiveRuntime?.model_name || config?.model || 'No model selected';
  const runtimeBaseUrl = effectiveRuntime?.base_url || config?.base_url;
  const runtimeStatus = offline ? 'Backend offline' : runtimeState.label;
  const runtimeColor = offline ? '#ef4444' : runtimeState.color;
  const scopedToSelectedSource = Boolean(selectedDocDetail?.source);
  const sourceLabel = scopedToSelectedSource
    ? 'Scoped to 1 source'
    : selectedDocId
    ? 'Source open'
    : 'No source selected';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '8px 20px',
        background: '#0f172a',
        borderBottom: '1px solid #1e293b',
        overflowX: 'auto',
        flexShrink: 0,
      }}
    >
      <span
        data-testid="context-mode"
        style={{
          padding: '3px 10px',
          borderRadius: '6px',
          fontSize: '11px',
          fontWeight: 700,
          background: `${modeColor}22`,
          border: `1px solid ${modeColor}66`,
          color: modeColor,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {modeLabel}
      </span>

      <div style={{ width: '1px', height: '16px', background: '#334155' }} />

      <span style={{ fontSize: '11px', color: scopedToSelectedSource ? '#cbd5e1' : '#64748b' }}>
        {sourceLabel}
      </span>

      <div style={{ width: '1px', height: '16px', background: '#334155' }} />

      <button
        type="button"
        data-testid="runtime-status"
        onClick={onSettingsClick}
        title={offline ? 'Backend offline - open settings to retry' : 'Open runtime settings'}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '7px',
          border: 'none',
          background: 'transparent',
          color: '#94a3b8',
          padding: 0,
          cursor: onSettingsClick ? 'pointer' : 'default',
          fontSize: '11px',
        }}
      >
        <span style={{ color: '#64748b', fontWeight: 700 }}>Runtime</span>
        <span style={{ color: '#cbd5e1', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {runtimeLabel}
        </span>
        <span
          style={{
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '10px',
            fontWeight: 700,
            background: `${runtimeColor}22`,
            border: `1px solid ${runtimeColor}66`,
            color: runtimeColor,
          }}
        >
          {runtimeStatus}
        </span>
      </button>

      {runtimeBaseUrl && (
        <>
          <div style={{ width: '1px', height: '16px', background: '#334155' }} />
          <span
            style={{
              fontSize: '10px',
              color: '#64748b',
              fontFamily: 'monospace',
              maxWidth: '220px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {runtimeBaseUrl}
          </span>
        </>
      )}
    </div>
  );
};
