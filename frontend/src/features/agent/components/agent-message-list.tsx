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
    if (!p) return '正在处理...';
    if (p.includes('retrieve') || p.includes('search')) return '正在检索文档...';
    if (p.includes('generate') || p.includes('synthesize')) return '正在生成回答...';
    if (p.includes('compare') || p.includes('summarize')) return '正在整理结果...';
    return '正在处理...';
  }, [events]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [artifacts, status]);

  if (!currentUserQuery && artifacts.length === 0 && status === 'idle') {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f4f4f5', flexDirection: 'column', padding: '24px' }}>
        <div style={{ maxWidth: '440px', textAlign: 'center', background: '#fff', padding: '40px', borderRadius: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.03)' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '16px', background: 'linear-gradient(135deg, #e0e7ff 0%, #ede9fe 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px auto', boxShadow: '0 4px 6px rgba(0,0,0,0.02)' }}>
            <span style={{ fontSize: '32px' }}>✨</span>
          </div>
          <h3 style={{ fontSize: '20px', fontWeight: '600', margin: '0 0 16px 0', color: '#1e293b', letterSpacing: '-0.01em' }}>欢迎使用 MindDock</h3>
          <p style={{ fontSize: '15px', color: '#475569', lineHeight: '1.7', margin: '0 0 24px 0', textAlign: 'left' }}>
            MindDock 是您的智能知识库助手，核心功能包括：<br/>
            <span style={{ display: 'inline-block', marginTop: '8px' }}>🔍 <strong>检索知识库</strong>：基于文档内容回答问题</span><br/>
            <span style={{ display: 'inline-block', marginTop: '4px' }}>📄 <strong>总结文档</strong>：提炼选中文件的主旨与要点</span><br/>
            <span style={{ display: 'inline-block', marginTop: '4px' }}>⚖️ <strong>对比资料</strong>：比对多份文档的异同与冲突</span>
          </p>
          <div style={{ fontSize: '13px', color: '#94a3b8' }}>
            在下方选择模式，并点击上方或此处的示例问题开始。
          </div>
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
            <div style={{ marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ background: taskType === 'compare' ? '#8b5cf6' : taskType === 'summarize' ? '#10b981' : '#3b82f6', color: '#fff', padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {taskType === 'compare' ? 'Compare Match' : taskType === 'summarize' ? 'Summary' : 'AI Response'}
              </span>
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: '500' }}>
                {taskType === 'compare' ? 'Compare Result' : taskType === 'summarize' ? 'Summary Result' : 'Chat Answer'}
              </span>
            </div>

            {/* Artifacts */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {artifacts.map((art, idx) => (
                <RawArtifactViewer key={idx} artifact={art} />
              ))}
            </div>

            {/* Thinking / Running Indicator */}
            {status === 'running' && (
              <div style={{ marginTop: artifacts.length > 0 ? '16px' : '0', padding: '16px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '12px', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.01)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '28px', height: '28px', background: '#3b82f6', borderRadius: '50%', color: '#fff' }}>
                  <svg viewBox="0 0 24 24" width="16" height="16" style={{ animation: 'spin 1.5s linear infinite' }}><path fill="currentColor" d="M12 2v4a6 6 0 00-6 6H2a10 10 0 0110-10z"/></svg>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '14px', fontWeight: '600', color: '#1e293b' }}>
                    {currentPhaseText}
                  </span>
                  <span style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>请稍候，AI正在为您准备数据</span>
                </div>
              </div>
            )}
            
            <style dangerouslySetInnerHTML={{__html:`
              @keyframes spin { 100% { transform: rotate(360deg); } }
            `}} />
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
};
