import React, { useEffect, useRef } from 'react';
import { useAgentStore } from '../store';
import { RawArtifactViewer } from './raw-artifact-viewer';

export const AgentMessageList: React.FC = () => {
  const { currentUserQuery, artifacts, status, taskType } = useAgentStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [artifacts, status]);

  if (!currentUserQuery && artifacts.length === 0 && status === 'idle') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f4f4f5', flexDirection: 'column' }}>
        <div style={{ maxWidth: '400px', textAlign: 'center' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '16px', background: 'linear-gradient(135deg, #e0e7ff 0%, #ede9fe 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px auto', boxShadow: '0 4px 6px rgba(0,0,0,0.02)' }}>
            <span style={{ fontSize: '32px' }}>✨</span>
          </div>
          <h3 style={{ fontSize: '20px', fontWeight: '600', margin: '0 0 12px 0', color: '#1e293b', letterSpacing: '-0.01em' }}>Welcome to MindDock</h3>
          <p style={{ fontSize: '14px', color: '#64748b', lineHeight: '1.6', margin: 0 }}>
            Select a task mode below and use the example prompts to start exploring your knowledge base.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px', background: '#f4f4f5' }}>
      <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* User Message */}
        {currentUserQuery && (
          <div style={{ alignSelf: 'flex-end', background: '#3b82f6', color: '#fff', padding: '12px 16px', borderRadius: '12px', borderTopRightRadius: '2px', maxWidth: '80%' }}>
            {currentUserQuery}
          </div>
        )}

        {/* Assistant Response Area */}
        {(artifacts.length > 0 || status === 'running') && (
          <div style={{ alignSelf: 'flex-start', background: '#fff', padding: '20px', borderRadius: '12px', borderTopLeftRadius: '2px', width: '100%', boxShadow: '0 1px 2px rgba(0,0,0,0.05)', boxSizing: 'border-box' }}>
            
            {/* Task Type Header */}
            {taskType !== 'chat' && (
              <div style={{ marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ background: taskType === 'compare' ? '#8b5cf6' : '#10b981', color: '#fff', padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {taskType === 'compare' ? 'Compare Match' : 'Summary'}
                </span>
                <span style={{ fontSize: '14px', color: '#64748b', fontWeight: '500' }}>
                  {taskType === 'compare' ? 'Compare Result' : 'Summary Result'}
                </span>
              </div>
            )}

            {/* Artifacts */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {artifacts.map((art, idx) => (
                <RawArtifactViewer key={idx} artifact={art} />
              ))}
            </div>

            {/* Thinking / Running Indicator */}
            {status === 'running' && (
              <div style={{ marginTop: artifacts.length > 0 ? '16px' : '0', color: '#64748b', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="dot-pulse">●●●</span>
              </div>
            )}
            
            <style dangerouslySetInnerHTML={{__html:`
              @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
              .dot-pulse { display: inline-block; animation: pulse 1.5s ease-in-out infinite; letter-spacing: 2px;}
            `}} />
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
};
