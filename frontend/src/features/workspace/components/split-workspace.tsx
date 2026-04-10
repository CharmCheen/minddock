import React from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { AgentPanel } from '../../agent/components/agent-panel';
import { SourceList } from './source-list';
import { AppHeader } from '../../../app/components/app-header';

export const SplitWorkspace: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <AppHeader />
      <PanelGroup direction="horizontal" style={{ flex: 1, width: '100vw', margin: 0, padding: 0 }}>
      <Panel defaultSize={35} minSize={20}>
        <SourceList />
      </Panel>
      <PanelResizeHandle style={{ width: '4px', backgroundColor: '#e2e8f0', cursor: 'col-resize', transition: 'background-color 0.2s', zIndex: 10 }} />
      <Panel defaultSize={65} minSize={30}>
        <AgentPanel />
      </Panel>
    </PanelGroup>
    </div>
  );
};
