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
  chat: 'var(--color-brand-600)',
  summarize: '#10b981',
  compare: '#8b5cf6',
};

interface ContextBarProps {
  onSettingsClick?: () => void;
}

export const ContextBar: React.FC<ContextBarProps> = ({ onSettingsClick }) => {
  const { taskType } = useAgentStore();
  const { selectedDocIds } = useWorkspaceStore();
  const { config, loadConfig, offline, loading } = useSettingsStore();

  useEffect(() => {
    if (offline) return;
    if (!config && !loading) {
      void loadConfig();
    }
  }, [config, offline, loadConfig, loading]);

  const modeColor = MODE_COLORS[taskType] || 'var(--color-text-tertiary)';
  const modeLabel = MODE_LABELS[taskType] || taskType;
  const runtimeState = deriveRuntimeStatus(config);
  const effectiveRuntime = config?.effective_runtime;
  const runtimeLabel = effectiveRuntime?.model_name || config?.model || 'No model';
  const runtimeStatus = offline ? 'Offline' : runtimeState.label;
  const runtimeColor = offline ? 'var(--color-error-text)' : runtimeState.color;
  const scopedToSelectedSource = selectedDocIds.length > 0;
  const sourceLabel = selectedDocIds.length === 0
    ? 'All sources'
    : selectedDocIds.length === 1
    ? '1 source selected'
    : `${selectedDocIds.length} sources selected`;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '8px 20px',
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border-subtle)',
        overflowX: 'auto',
        flexShrink: 0,
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      {/* Mode badge */}
      <span
        data-testid="context-mode"
        style={{
          padding: '3px 10px',
          borderRadius: 'var(--radius-sm)',
          fontSize: '11px',
          fontWeight: 700,
          background: `${modeColor}11`,
          border: `1px solid ${modeColor}33`,
          color: modeColor,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          flexShrink: 0,
        }}
      >
        {modeLabel}
      </span>

      <div style={{ width: '1px', height: '14px', background: 'var(--color-border-subtle)', flexShrink: 0 }} />

      {/* Source scope */}
      <span style={{
        fontSize: '12px',
        color: scopedToSelectedSource ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
        fontWeight: scopedToSelectedSource ? 500 : 400,
        whiteSpace: 'nowrap',
      }}>
        {sourceLabel}
      </span>

      <div style={{ flex: 1 }} />

      {/* Runtime status */}
      <button
        type="button"
        data-testid="runtime-status"
        onClick={onSettingsClick}
        title={offline ? 'Backend offline - open settings to retry' : 'Open runtime settings'}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '8px',
          border: 'none',
          background: 'transparent',
          color: 'var(--color-text-secondary)',
          padding: '4px 8px',
          cursor: onSettingsClick ? 'pointer' : 'default',
          fontSize: '12px',
          borderRadius: 'var(--radius-sm)',
          transition: 'background var(--transition-fast)',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}
        onMouseOver={(e) => { if (onSettingsClick) e.currentTarget.style.background = 'var(--color-canvas)'; }}
        onMouseOut={(e) => { e.currentTarget.style.background = 'transparent'; }}
      >
        <span style={{ color: 'var(--color-text-tertiary)', fontWeight: 500 }}>{runtimeLabel}</span>
        <span
          style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: runtimeColor,
            flexShrink: 0,
          }}
        />
        <span style={{
          fontSize: '11px',
          fontWeight: 600,
          color: runtimeColor,
        }}>
          {runtimeStatus}
        </span>
      </button>
    </div>
  );
};
