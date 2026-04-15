import { create } from 'zustand';
import { RuntimeConfigResponse } from '../../core/types/api';
import { RuntimeConfigService } from '../../lib/api/services/runtime-config';

interface SettingsState {
  config: RuntimeConfigResponse | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  successMessage: string | null;

  loadConfig: () => Promise<void>;
  saveConfig: (config: {
    provider: string;
    base_url: string;
    api_key: string;
    model: string;
    enabled: boolean;
  }) => Promise<void>;
  clearMessages: () => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  config: null,
  loading: false,
  saving: false,
  error: null,
  successMessage: null,

  loadConfig: async () => {
    set({ loading: true, error: null });
    try {
      const config = await RuntimeConfigService.getConfig();
      set({ config, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load runtime config';
      set({ error: message, loading: false });
    }
  },

  saveConfig: async (config) => {
    set({ saving: true, error: null, successMessage: null });
    try {
      const updated = await RuntimeConfigService.updateConfig(config);
      set({ config: updated, saving: false, successMessage: 'Runtime configuration saved successfully.' });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save runtime config';
      set({ error: message, saving: false });
    }
  },

  clearMessages: () => set({ error: null, successMessage: null }),
}));
