import React, { useEffect, useRef, useState } from 'react';
import { useAgentStore } from '../store';
import type { ConversationTurn } from '../types';
import { RawArtifactViewer } from './raw-artifact-viewer';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';
import { IconSearch } from '../../../components/ui/icons';

const PHASE_LABELS: Record<string, string> = {
  preparing: 'Preparing',
  resolving_runtime: 'Resolving runtime',
  retrieving: 'Retrieving sources',
  generating: 'Generating answer',
  finalizing: 'Finalizing output',
};

const TURN_PHASE_LABELS: Record<string, string> = {
  preparing: 'Preparing',
  resolving_runtime: 'Loading model',
  retrieving: 'Finding relevant sources',
  generating: 'Generating answer',
  finalizing: 'Finalizing response',
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const TurnWorkflowDetails: React.FC<{ turn: ConversationTurn; density: 'compact' | 'comfortable' }> = ({ turn, density }) => {
  const d = density;
  return (
    <div style={{
      maxHeight: '200px',
      overflowY: 'auto',
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border-subtle)',
      borderRadius: '0 0 var(--radius-md) var(--radius-md)',
      padding: d === 'compact' ? '10px 14px' : '12px 16px',
      marginTop: '-4px',
      paddingTop: '14px',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', fontWeight: 600, marginBottom: '8px', letterSpacing: '0.02em' }}>
        What happened ({turn.events.length} step{turn.events.length === 1 ? '' : 's'})
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {turn.events.slice().reverse().slice(0, 20).map((event, index) => (
          <div
            key={`${event.event}-${index}`}
            style={{
              fontSize: '12px',
              color: 'var(--color-text-secondary)',
              padding: '6px 10px',
              background: 'var(--color-canvas-subtle)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border-subtle)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: event.event === 'progress' ? 'var(--color-brand-500)' : event.event === 'artifact' ? 'var(--color-success-text)' : event.event === 'failed' ? 'var(--color-error-text)' : 'var(--color-text-tertiary)',
              flexShrink: 0,
            }} />
            <span style={{ fontWeight: 500 }}>
              {event.event === 'progress'
                ? (TURN_PHASE_LABELS[(event.data as { phase?: string })?.phase || ''] ?? (event.data as { phase?: string })?.phase)
                : event.event === 'run_started'
                ? 'Started'
                : event.event === 'artifact'
                ? 'Answer ready'
                : event.event === 'completed'
                ? 'Done'
                : event.event === 'failed'
                ? 'Failed'
                : event.event}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const TurnView: React.FC<{ turn: ConversationTurn; isActive: boolean; density: 'compact' | 'comfortable' }> = ({ turn, isActive, density }) => {
  const [showDetails, setShowDetails] = useState(false);
  const d = density;

  const visibleArtifacts = React.useMemo(() => {
    if (turn.taskType !== 'compare') {
      return turn.artifacts;
    }
    const structuredCompare = turn.artifacts.find((artifact) => {
      const content = artifact.content as { schema_name?: string } | undefined;
      return artifact.kind === 'structured_json' && content?.schema_name === 'compare.v1';
    });
    return structuredCompare ? [structuredCompare] : turn.artifacts;
  }, [turn.artifacts, turn.taskType]);

  const currentProgress = [...turn.events].reverse().find((event) => event.event === 'progress');
  const rawPhase = (currentProgress?.data as { phase?: string } | undefined)?.phase;
  const currentPhaseText = rawPhase ? PHASE_LABELS[rawPhase] ?? rawPhase : null;

  const taskLabel = turn.taskType === 'compare' ? 'Compare' : turn.taskType === 'summarize' ? 'Summarize' : 'Chat';
  const resultLabel = turn.taskType === 'compare' ? 'Document Comparison Result' : turn.taskType === 'summarize' ? 'Summary Result' : 'AI Response';

  const statusBadgeConfig: Record<string, { color: string; bg: string; label: string }> = {
    completed: { color: 'var(--color-success-text)', bg: 'var(--color-success-bg)', label: 'Completed' },
    failed: { color: 'var(--color-error-text)', bg: 'var(--color-error-bg)', label: 'Failed' },
    cancelled: { color: '#b45309', bg: 'var(--color-warning-bg)', label: 'Cancelled' },
  };

  const cfg = statusBadgeConfig[turn.status];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: d === 'compact' ? '16px' : '24px', animation: 'fadeSlideUp 250ms ease-out forwards' }}>
      {/* User message */}
      <div style={{ alignSelf: 'flex-end', maxWidth: '80%' }}>
        <div style={{
          background: 'var(--color-brand-600)',
          color: '#fff',
          padding: d === 'compact' ? '10px 14px' : '12px 18px',
          borderRadius: '18px',
          borderBottomRightRadius: '6px',
          fontSize: '14px',
          lineHeight: 1.6,
          boxShadow: 'var(--shadow-md)',
        }}>
          {turn.query}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', marginTop: '4px', textAlign: 'right', paddingRight: '4px' }}>
          You · {formatTime(turn.createdAt)}
        </div>
      </div>

      {/* AI Response */}
      <div style={{ alignSelf: 'flex-start', width: '100%', display: 'flex', flexDirection: 'column', gap: d === 'compact' ? '12px' : '16px' }}>
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: d === 'compact' ? '8px' : '10px', minHeight: '28px', flexWrap: 'wrap' }}>
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: d === 'compact' ? '3px 10px' : '4px 12px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.04em',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-subtle)',
            color: turn.taskType === 'compare' ? '#8b5cf6' : turn.taskType === 'summarize' ? '#10b981' : 'var(--color-brand-600)',
            textTransform: 'uppercase',
            boxShadow: 'var(--shadow-sm)',
          }}>
            {taskLabel}
          </span>
          <span style={{ fontSize: '14px', color: 'var(--color-text-primary)', fontWeight: 600, letterSpacing: '0.01em' }}>{resultLabel}</span>

          {/* Status badge for completed/failed/cancelled turns */}
          {!isActive && cfg && (
            <span style={{
              fontSize: '10px',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              background: cfg.bg,
              color: cfg.color,
              letterSpacing: '0.03em',
              textTransform: 'uppercase',
            }}>
              {cfg.label}
            </span>
          )}
        </div>

        {/* Running state */}
        {isActive && turn.status === 'running' && visibleArtifacts.length === 0 && (
          <div style={{
            padding: d === 'compact' ? '14px 16px' : '18px 20px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            alignItems: 'center',
            gap: d === 'compact' ? '10px' : '14px',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <svg viewBox="0 0 24 24" width="22" height="22" style={{ animation: 'spin 1.4s linear infinite', color: 'var(--color-brand-600)', flexShrink: 0 }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" />
            </svg>
            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
              {currentPhaseText ?? 'Processing...'}
            </span>
          </div>
        )}

        {isActive && turn.status === 'running' && currentPhaseText && visibleArtifacts.length === 0 && (
          <div style={{
            padding: d === 'compact' ? '12px 14px' : '14px 16px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            alignItems: 'center',
            gap: d === 'compact' ? '10px' : '12px',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <svg viewBox="0 0 24 24" width="18" height="18" style={{ animation: 'spin 1.2s linear infinite', color: 'var(--color-brand-500)', flexShrink: 0 }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" />
            </svg>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>{currentPhaseText}</span>
              <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', marginTop: '2px' }}>Working on the current run</span>
            </div>
          </div>
        )}

        {/* Artifacts */}
        {visibleArtifacts.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: d === 'compact' ? '14px' : '20px' }}>
            {visibleArtifacts.map((artifact, index) => (
              <RawArtifactViewer key={artifact.artifact_id || index} artifact={artifact} />
            ))}
          </div>
        )}

        {/* Active turn still running with artifacts */}
        {isActive && turn.status === 'running' && visibleArtifacts.length > 0 && (
          <div style={{
            padding: d === 'compact' ? '12px 14px' : '14px 16px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            alignItems: 'center',
            gap: d === 'compact' ? '10px' : '12px',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <svg viewBox="0 0 24 24" width="16" height="16" style={{ animation: 'spin 1.2s linear infinite', color: 'var(--color-brand-500)', flexShrink: 0 }}>
              <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" />
            </svg>
            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>{currentPhaseText ?? 'Processing...'}</span>
          </div>
        )}

        {/* Error state */}
        {turn.status === 'failed' && turn.error && (
          <div style={{
            padding: d === 'compact' ? '12px 14px' : '14px 16px',
            background: 'var(--color-error-bg)',
            border: '1px solid var(--color-error-border)',
            borderRadius: 'var(--radius-lg)',
            color: 'var(--color-error-text)',
            fontSize: '13px',
            lineHeight: 1.5,
          }}>
            {turn.error}
          </div>
        )}

        {/* Cancelled state */}
        {turn.status === 'cancelled' && (
          <div style={{
            padding: d === 'compact' ? '12px 14px' : '14px 16px',
            background: 'var(--color-warning-bg)',
            border: '1px solid var(--color-warning-border)',
            borderRadius: 'var(--radius-lg)',
            color: '#b45309',
            fontSize: '13px',
            lineHeight: 1.5,
          }}>
            {turn.error || 'Cancelled by user'}
          </div>
        )}

        {/* Workflow details toggle per turn */}
        {turn.events.length > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setShowDetails(!showDetails)}
              style={{
                fontSize: '11px',
                color: 'var(--color-text-tertiary)',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                cursor: 'pointer',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 500,
                transition: 'all var(--transition-fast)',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.color = 'var(--color-text-secondary)';
                e.currentTarget.style.borderColor = 'var(--color-border-default)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.color = 'var(--color-text-tertiary)';
                e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
              }}
            >
              {showDetails ? 'Hide details' : 'Show details'}
            </button>
            {showDetails && <TurnWorkflowDetails turn={turn} density={density} />}
          </div>
        )}
      </div>

      {/* Turn separator */}
      <div style={{ borderTop: '1px solid var(--color-border-subtle)', marginTop: d === 'compact' ? '8px' : '12px', opacity: 0.6 }} />
    </div>
  );
};

export const AgentMessageList: React.FC = () => {
  const { turns, status, activeTurnId, clearConversation } = useAgentStore();
  const { density } = useWorkspacePreferences();
  const endRef = useRef<HTMLDivElement>(null);

  const d = density;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns, status]);

  if (turns.length === 0 && status === 'idle') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--color-canvas)', flexDirection: 'column', padding: d === 'compact' ? '16px' : '24px' }}>
        <div style={{ textAlign: 'center', marginBottom: d === 'compact' ? '20px' : '28px' }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '14px',
            background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px',
            fontSize: '22px',
            color: '#fff',
            boxShadow: 'var(--shadow-md)',
          }}>
            <IconSearch size={22} />
          </div>
          <h3 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 8px 0' }}>
            MindDock Knowledge Workspace
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--color-text-tertiary)', margin: '0 0 4px', maxWidth: '420px', lineHeight: 1.5 }}>
            Ask questions, summarize, or compare across your indexed sources.
            Every answer includes verifiable citations.
          </p>
        </div>

        <div style={{ display: 'flex', gap: d === 'compact' ? '8px' : '12px', flexWrap: 'wrap', justifyContent: 'center', maxWidth: '640px' }}>
          {[
            { title: 'Chat', desc: 'Ask questions about your documents', color: '#3b82f6', bg: '#eff6ff', border: '#bfdbfe' },
            { title: 'Summarize', desc: 'Extract key points from selected sources', color: '#10b981', bg: '#f0fdf4', border: '#bbf7d0' },
            { title: 'Compare', desc: 'Compare views and find conflicts', color: '#8b5cf6', bg: '#f5f3ff', border: '#ddd6fe' },
          ].map((item) => (
            <div
              key={item.title}
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 'var(--radius-lg)',
                padding: d === 'compact' ? '14px 16px' : '18px 20px',
                flex: '1 1 170px',
                maxWidth: '210px',
                boxShadow: 'var(--shadow-sm)',
                transition: 'all var(--transition-fast)',
                cursor: 'default',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                e.currentTarget.style.borderColor = item.border;
                e.currentTarget.style.transform = 'translateY(-2px)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
                e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              <div style={{
                fontSize: '12px',
                fontWeight: 700,
                color: item.color,
                marginBottom: '6px',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}>{item.title}</div>
              <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>{item.desc}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: d === 'compact' ? '20px' : '28px', display: 'grid', gap: d === 'compact' ? '6px' : '8px', maxWidth: '520px', width: '100%' }}>
          <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', textAlign: 'center', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Supported Source Skills
          </div>
          <div style={{ display: 'flex', gap: d === 'compact' ? '6px' : '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
            {['PDF', 'Markdown', 'TXT', 'URL', 'Image OCR', 'CSV'].map((skill) => (
              <span key={skill} style={{
                fontSize: '11px',
                color: 'var(--color-text-secondary)',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                padding: d === 'compact' ? '3px 10px' : '4px 12px',
                borderRadius: 'var(--radius-full)',
                boxShadow: 'var(--shadow-sm)',
              }}>
                {skill}
              </span>
            ))}
          </div>
        </div>

        <div style={{ marginTop: d === 'compact' ? '14px' : '20px', fontSize: '12px', color: 'var(--color-text-tertiary)', textAlign: 'center', maxWidth: '420px', lineHeight: 1.5 }}>
          Select sources from the left panel to focus retrieval, or ask across all sources.
          Citations open the source drawer so you can verify every claim.
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: d === 'compact' ? '16px 16px 12px' : '24px 24px 20px', background: 'var(--color-canvas)' }}>
      <div style={{ maxWidth: '820px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: d === 'compact' ? '16px' : '24px' }}>
        {/* Conversation header */}
        {turns.length > 0 && (
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: d === 'compact' ? '8px 12px' : '10px 14px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
              {turns.length} turn{turns.length === 1 ? '' : 's'}
            </span>
            <button
              type="button"
              data-testid="clear-conversation"
              onClick={clearConversation}
              style={{
                fontSize: '12px',
                color: 'var(--color-text-tertiary)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 500,
                transition: 'all var(--transition-fast)',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.color = 'var(--color-error-text)';
                e.currentTarget.style.background = 'var(--color-error-bg)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.color = 'var(--color-text-tertiary)';
                e.currentTarget.style.background = 'transparent';
              }}
            >
              Clear conversation
            </button>
          </div>
        )}

        {turns.map((turn) => (
          <TurnView
            key={turn.id}
            turn={turn}
            isActive={turn.id === activeTurnId && (status === 'running' || status === 'cancelling')}
            density={d}
          />
        ))}

        <div ref={endRef} />
      </div>
    </div>
  );
};
