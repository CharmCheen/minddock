import React, { useEffect, useRef } from 'react';
import { useAgentStore } from '../store';
import { RawArtifactViewer } from './raw-artifact-viewer';

const PHASE_LABELS: Record<string, string> = {
  preparing: 'Preparing',
  resolving_runtime: 'Resolving runtime',
  retrieving: 'Retrieving sources',
  generating: 'Generating answer',
  finalizing: 'Finalizing output',
};

export const AgentMessageList: React.FC = () => {
  const { currentUserQuery, artifacts, status, taskType, events } = useAgentStore();
  const endRef = useRef<HTMLDivElement>(null);

  const currentProgress = [...events].reverse().find((event) => event.event === 'progress');
  const rawPhase = (currentProgress?.data as { phase?: string } | undefined)?.phase;
  const currentPhaseText = rawPhase ? PHASE_LABELS[rawPhase] ?? rawPhase : null;
  const visibleArtifacts = React.useMemo(() => {
    if (taskType !== 'compare') {
      return artifacts;
    }
    const structuredCompare = artifacts.find((artifact) => {
      const content = artifact.content as { schema_name?: string } | undefined;
      return artifact.kind === 'structured_json' && content?.schema_name === 'compare.v1';
    });
    return structuredCompare ? [structuredCompare] : artifacts;
  }, [artifacts, taskType]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [visibleArtifacts, status]);

  if (!currentUserQuery && artifacts.length === 0 && status === 'idle') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f4f4f5', flexDirection: 'column', padding: '24px' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#0f172a', margin: '0 0 6px 0' }}>
            Ask your knowledge base anything
          </h3>
          <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
            Answers include citations from your sources
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center', maxWidth: '560px' }}>
          {[
            ['Chat', 'Ask questions about your documents'],
            ['Summarize', 'Extract key points from a source'],
            ['Compare', 'Compare views across sources'],
          ].map(([title, body]) => (
            <div
              key={title}
              style={{
                background: '#fff',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                padding: '16px 20px',
                flex: '1 1 160px',
                maxWidth: '200px',
                boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
              }}
            >
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>{title}</div>
              <div style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.5 }}>{body}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: '24px', fontSize: '12px', color: '#94a3b8', textAlign: 'center' }}>
          Select a source from the left panel, then choose a mode and ask below
        </div>
      </div>
    );
  }

  const taskLabel = taskType === 'compare' ? 'Compare' : taskType === 'summarize' ? 'Summary' : 'Chat';
  const resultLabel = taskType === 'compare' ? 'Document Comparison Result' : taskType === 'summarize' ? 'Summary Result' : 'AI Response';

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 28px 24px', background: '#f4f4f5' }}>
      <div style={{ maxWidth: '820px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {currentUserQuery && (
          <div style={{ alignSelf: 'flex-end', maxWidth: '80%' }}>
            <div
              style={{
                background: '#3b82f6',
                color: '#fff',
                padding: '12px 18px',
                borderRadius: '16px',
                borderBottomRightRadius: '4px',
                fontSize: '14px',
                lineHeight: 1.6,
                boxShadow: '0 2px 8px rgba(59, 130, 246, 0.25)',
              }}
            >
              {currentUserQuery}
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px', textAlign: 'right', paddingRight: '4px' }}>
              You
            </div>
          </div>
        )}

        {(visibleArtifacts.length > 0 || status === 'running') && (
          <div
            style={{
              alignSelf: 'flex-start',
              background: 'transparent',
              padding: '0',
              width: '100%',
              boxShadow: 'none',
              border: 'none',
              borderLeft: '2px solid #3b82f6',
              paddingLeft: '18px',
              display: 'flex',
              flexDirection: 'column',
              gap: '18px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minHeight: '26px' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  background: 'transparent',
                  border: '1px solid currentColor',
                  color: taskType === 'compare' ? '#8b5cf6' : taskType === 'summarize' ? '#10b981' : '#3b82f6',
                  textTransform: 'uppercase',
                }}
              >
                {taskLabel}
              </span>
              <span style={{ fontSize: '14px', color: '#1e293b', fontWeight: 500, letterSpacing: '0.01em' }}>{resultLabel}</span>
            </div>

            {status === 'running' && visibleArtifacts.length === 0 && (
              <div
                style={{
                  padding: '18px 20px',
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                }}
              >
                <svg viewBox="0 0 24 24" width="22" height="22" style={{ animation: 'spin 1.4s linear infinite', color: '#2563eb', flexShrink: 0 }}>
                  <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" />
                </svg>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                  {currentPhaseText ?? 'Processing...'}
                </span>
              </div>
            )}

            {status === 'running' && currentPhaseText && (
              <div style={{ padding: '14px 16px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <svg viewBox="0 0 24 24" width="18" height="18" style={{ animation: 'spin 1.2s linear infinite', color: '#3b82f6', flexShrink: 0 }}>
                  <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" />
                </svg>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>{currentPhaseText}</span>
                  <span style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>Working on the current run</span>
                </div>
              </div>
            )}

            {visibleArtifacts.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {visibleArtifacts.map((artifact, index) => (
                  <RawArtifactViewer key={artifact.artifact_id || index} artifact={artifact} />
                ))}
              </div>
            )}

            {status === 'running' && visibleArtifacts.length > 0 && (
              <div style={{ padding: '14px 16px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <svg viewBox="0 0 24 24" width="16" height="16" style={{ animation: 'spin 1.2s linear infinite', color: '#3b82f6', flexShrink: 0 }}>
                  <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z" />
                </svg>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>{currentPhaseText ?? 'Processing...'}</span>
              </div>
            )}
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
};
