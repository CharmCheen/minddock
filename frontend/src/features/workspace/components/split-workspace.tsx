import React, { useState } from 'react';
import { AgentPanel } from '../../agent/components/agent-panel';
import { SourceList } from './source-list';
import { SourceDrawer } from './source-drawer';
import { AppHeader } from '../../../app/components/app-header';
import { SettingsView } from '../../../features/settings/settings-view';
import { useBackendStartup } from '../../../features/app/hooks/useBackendStartup';
import { useSettingsStore } from '../../../features/settings/store';

export const SplitWorkspace: React.FC = () => {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { setOnline, setOffline } = useSettingsStore();

  useBackendStartup({
    onOnline: () => setOnline(),
    onOffline: () => setOffline(),
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <AppHeader onSettingsClick={() => setSettingsOpen(true)} />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: Source List sidebar */}
        <div style={{
          width: '280px',
          minWidth: '220px',
          maxWidth: '360px',
          borderRight: '1px solid #e2e8f0',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: '#fff',
        }}>
          <SourceList />
        </div>

        {/* Right: Main workspace */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <AgentPanel onSettingsClick={() => setSettingsOpen(true)} />
        </div>
      </div>

      {/* Source detail drawer reads drawerOpen from workspaceStore. */}
      <SourceDrawer />

      {settingsOpen && <SettingsView onClose={() => setSettingsOpen(false)} />}
    </div>
  );
};
