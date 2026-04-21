import React from 'react';

interface AppHeaderProps {
  onSettingsClick?: () => void;
}

export const AppHeader: React.FC<AppHeaderProps> = ({ onSettingsClick }) => {
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
        {/* Settings gear */}
        <button
          onClick={onSettingsClick}
          title="Runtime Settings"
          aria-label="Open settings"
          data-testid="settings-button"
          style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'color 0.2s, background 0.2s' }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#e2e8f0'; (e.currentTarget as HTMLButtonElement).style.background = '#1e293b'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = '#94a3b8'; (e.currentTarget as HTMLButtonElement).style.background = 'none'; }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>

        <div style={{ fontSize: '12px', color: '#cbd5e1', background: '#1e293b', padding: '4px 10px', borderRadius: '120px', border: '1px solid #334155' }}>
          Beta V0.1
        </div>
      </div>
    </div>
  );
};
