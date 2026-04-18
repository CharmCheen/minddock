/// <reference types="vite/client" />

interface MermaidGlobal {
  run: (opts: { nodes: HTMLElement[] }) => void;
  initialize: (opts: { startOnLoad: boolean }) => void;
}

declare interface Window {
  mermaid?: MermaidGlobal;
}
