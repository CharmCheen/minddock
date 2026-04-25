import React from 'react';

interface AppHeaderProps {
  onSettingsClick?: () => void;
}

export const AppHeader: React.FC<AppHeaderProps> = ({ onSettingsClick }) => {
  return (
    <div style={{
      height: '52px',
      background: 'var(--color-surface)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 20px',
      color: 'var(--color-text-primary)',
      boxShadow: 'var(--shadow-sm)',
      zIndex: 50,
      borderBottom: '1px solid var(--color-border-subtle)',
    }}>
      {/* Logo / Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div style={{
          width: '28px',
          height: '28px',
          borderRadius: '8px',
          background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 'bold',
          fontSize: '15px',
          color: '#fff',
          boxShadow: '0 2px 6px rgba(59, 130, 246, 0.3)',
        }}>
          M
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h1 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>MindDock</h1>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Right side utility */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--color-text-tertiary)',
          fontWeight: 500,
          letterSpacing: '0.02em',
        }}>
          AI Knowledge Workspace
        </span>

        <div style={{ width: '1px', height: '16px', background: 'var(--color-border-subtle)' }} />

        {/* Settings gear */}
        <button
          onClick={onSettingsClick}
          title="Settings"
          aria-label="Open settings"
          data-testid="settings-button"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text-tertiary)',
            cursor: 'pointer',
            padding: '6px',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all var(--transition-fast)',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-secondary)';
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-canvas)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-tertiary)';
            (e.currentTarget as HTMLButtonElement).style.background = 'none';
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>

        <div style={{
          fontSize: '11px',
          color: 'var(--color-text-tertiary)',
          background: 'var(--color-canvas)',
          padding: '3px 10px',
          borderRadius: 'var(--radius-full)',
          border: '1px solid var(--color-border-subtle)',
          fontWeight: 500,
        }}>
          Beta
        </div>
      </div>
    </div>
  );
};
