import React from 'react';

export const AppHeader: React.FC = () => {
  return (
    <div style={{ height: '56px', background: '#0f172a', display: 'flex', alignItems: 'center', padding: '0 24px', color: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', zIndex: 50 }}>
      {/* Logo / Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ width: '28px', height: '28px', borderRadius: '6px', background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold', fontSize: '16px' }}>
          M
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h1 style={{ margin: 0, fontSize: '16px', fontWeight: '600', letterSpacing: '0.02em' }}>MindDock</h1>
          <span style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>AI Knowledge Workspace</span>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Right side utility icons / avatar placeholder */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ fontSize: '12px', color: '#cbd5e1', background: '#1e293b', padding: '4px 10px', borderRadius: '120px', border: '1px solid #334155' }}>
          Beta V0.1
        </div>
      </div>
    </div>
  );
};
