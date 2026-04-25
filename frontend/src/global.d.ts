interface MindDockWindowConfig {
  apiBaseUrl?: string;
}

interface Window {
  __MINDDOCK_CONFIG__?: MindDockWindowConfig;
}
