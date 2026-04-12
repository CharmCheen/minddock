import React, { useEffect, useRef, useMemo } from 'react';
import { useAgentStore } from '../store';
import { RawArtifactViewer } from './raw-artifact-viewer';

export const AgentMessageList: React.FC = () => {
  const { currentUserQuery, artifacts, status, taskType, events } = useAgentStore();
  const endRef = useRef<HTMLDivElement>(null);

  // Derive current phase text from events reactively — recomputes whenever events change
  const currentPhaseText = useMemo(() => {
    const currentProgress = [...events].reverse().find(e => e.event === 'progress');
    const p = (currentProgress?.data as any)?.phase as string | undefined;
    if (!p) return 'Processing...';
    if (p.includes('retrieve') || p.includes('search')) return 'Searching documents...';
    if (p.includes('generate') || p.includes('synthesize')) return 'Generating response...';
    if (p.includes('compare') || p.includes('summarize')) return 'Comparing results...';
    return 'Processing...';
  }, [events]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [artifacts, status]);

  if (!currentUserQuery && artifacts.length === 0 && status === 'idle') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f4f4f5', flexDirection: 'column', padding: '24px' }}>
        <div style={{ maxWidth: '480px', textAlign: 'center', background: '#fff', padding: '48px 40px', borderRadius: '20px', boxShadow: '0 8px 32px rgba(0,0,0,0.06)' }}>
          <div style={{ width: '72px', height: '72px', borderRadius: '20px', background: 'linear-gradient(135deg, #e0e7ff 0%, #ede9fe 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px auto', boxShadow: '0 8px 16px rgba(0,0,0,0.06)' }}>
            <span style={{ fontSize: '36px' }}>✨</span>
          </div>
          <h3 style={{ fontSize: '22px', fontWeight: '600', margin: '0 0 16px 0', color: '#1e293b', letterSpacing: '-0.01em' }}>Welcome to MindDock</h3>
          <p style={{ fontSize: '15px', color: '#475569', lineHeight: '1.7', margin: '0 0 28px 0', textAlign: 'left' }}>
            MindDock is your intelligent knowledge assistant. Core features:
          </p>
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            textAlign: 'left',
            background: '#f8fafc',
            padding: '20px',
            borderRadius: '12px',
            marginBottom: '28px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '14px', color: '#334155' }}>
              <span style={{ fontSize: '20px' }}>🔍</span>
              <span><strong>Search Knowledge Base</strong> — Ask questions based on your documents</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '14px', color: '#334155' }}>
              <span style={{ fontSize: '20px' }}>📄</span>
              <span><strong>Summarize Documents</strong> — Extract key points from selected files</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '14px', color: '#334155' }}>
              <span style={{ fontSize: '20px' }}>⚖️</span>
              <span><strong>Compare Sources</strong> — Find similarities and conflicts between documents</span>
            </div>
          </div>
          <div style={{ fontSize: '13px', color: '#94a3b8' }}>
            Select a mode below and try the example prompts to get started
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px', background: '#f4f4f5' }}>
      <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* User Message */}
        {currentUserQuery && (
          <div style={{ alignSelf: 'flex-end', maxWidth: '80%' }}>
            <div style={{
              background: '#3b82f6',
              color: '#fff',
              padding: '12px 18px',
              borderRadius: '16px',
              borderBottomRightRadius: '4px',
              fontSize: '14px',
              lineHeight: '1.6',
              boxShadow: '0 2px 8px rgba(59, 130, 246, 0.25)'
            }}>
              {currentUserQuery}
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px', textAlign: 'right', paddingRight: '4px' }}>
              You
            </div>
          </div>
        )}

        {/* Assistant Response Area */}
        {(artifacts.length > 0 || status === 'running') && (
          <div style={{
            alignSelf: 'flex-start',
            background: '#fff',
            padding: '16px 20px',
            borderRadius: '12px',
            width: '100%',
            boxShadow: '0 1px 4px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.03)',
          }}>

            {/* Task Type Header */}
            <div style={{
              marginBottom: '16px',
              paddingBottom: '12px',
              borderBottom: '1px solid #f1f5f9',
              display: 'flex',
              alignItems: 'center',
              gap: '10px'
            }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '5px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: '700',
                letterSpacing: '0.04em',
                background: taskType === 'compare' ? '#8b5cf6' : taskType === 'summarize' ? '#10b981' : '#3b82f6',
                color: '#fff',
                textTransform: 'uppercase'
              }}>
                {taskType === 'compare' ? '⚖ Compare' : taskType === 'summarize' ? '📝 Summary' : '💬 Chat'}
              </span>
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: '400' }}>
                {taskType === 'compare' ? 'Document Comparison Result' : taskType === 'summarize' ? 'Summary Result' : 'AI Response'}
              </span>
            </div>

            {/* Artifacts */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {artifacts.map((art, idx) => (
                <RawArtifactViewer key={idx} artifact={art} />
              ))}
            </div>

            {/* Thinking / Running Indicator */}
            {status === 'running' && (
              <div style={{
                marginTop: artifacts.length > 0 ? '20px' : '0',
                padding: '20px',
                background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '36px',
                  height: '36px',
                  background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
                  borderRadius: '50%',
                  color: '#fff',
                  boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)'
                }}>
                  <svg viewBox="0 0 24 24" width="18" height="18" style={{ animation: 'spin 1.2s linear infinite' }}>
                    <path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z"/>
                  </svg>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '14px', fontWeight: '600', color: '#1e293b' }}>
                    {currentPhaseText}
                  </span>
                  <span style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>Please wait while AI prepares your data</span>
                </div>
              </div>
            )}
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
};
