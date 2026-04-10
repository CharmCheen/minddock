import React from 'react';
import ReactDOM from 'react-dom/client';
import { SplitWorkspace } from './features/workspace/components/split-workspace';

const App = () => {
  return <SplitWorkspace />;
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
