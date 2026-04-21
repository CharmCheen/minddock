import { create } from 'zustand';
import { RuntimeConfigResponse } from '../../core/types/api';
import { RuntimeConfigService } from '../../lib/api/services/runtime-config';

export interface RuntimeFormValues {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  enabled: boolean;
}

interface TestResult {
  success: boolean;
  message: string;
  errorKind: string | null;
}

interface SettingsState {
  // --- Runtime state ---
  config: RuntimeConfigResponse | null;     // what is currently ACTIVE (from last save/reset)
  loading: boolean;
  saving: boolean;
  testing: boolean;
  resetting: boolean;
  error: string | null;
  successMessage: string | null;

  // --- Test result (persists until form changes or reset) ---
  testResult: TestResult | null;
  testTimestamp: number | null;             // Date.now() of last test

  // --- Form editing state ---
  formValues: RuntimeFormValues;
  isDirty: boolean;                        // true when form differs from last saved config

  // --- Actions ---
  loadConfig: () => Promise<void>;
  saveConfig: (form: RuntimeFormValues) => Promise<void>;
  testConnection: (form: Omit<RuntimeFormValues, 'enabled'>) => Promise<void>;
  resetConfig: () => Promise<void>;
  updateFormValues: (form: RuntimeFormValues) => void;
  clearMessages: () => void;
}

const DEFAULT_FORM: RuntimeFormValues = {
  provider: 'openai_compatible',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o-mini',
  enabled: false,
};

function formFromConfig(config: RuntimeConfigResponse | null, hasStoredKey: boolean): RuntimeFormValues {
  if (!config) return { ...DEFAULT_FORM };
  return {
    provider: config.provider,
    base_url: config.base_url,
    model: config.model,
    enabled: config.enabled,
    api_key: hasStoredKey ? '••••••••' : '',
  };
}

function computeIsDirty(current: RuntimeFormValues, saved: RuntimeFormValues): boolean {
  return (
    current.provider !== saved.provider ||
    current.base_url !== saved.base_url ||
    current.model !== saved.model ||
    current.enabled !== saved.enabled ||
    // api_key field: treat placeholder as unchanged; any real change makes it dirty
    (current.api_key !== '' && current.api_key !== saved.api_key && current.api_key !== '••••••••')
  );
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  config: null,
  loading: false,
  saving: false,
  testing: false,
  resetting: false,
  error: null,
  successMessage: null,
  testResult: null,
  testTimestamp: null,
  formValues: { ...DEFAULT_FORM },
  isDirty: false,

  loadConfig: async () => {
    set({ loading: true, error: null });
    try {
      const config = await RuntimeConfigService.getConfig();
      const hasStoredKey = config.api_key_masked;
      const formValues = formFromConfig(config, hasStoredKey);
      set({
        config,
        formValues,
        isDirty: false,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load runtime config';
      set({ error: message, loading: false });
    }
  },

  saveConfig: async (form) => {
    set({ saving: true, error: null, successMessage: null });
    try {
      const updated = await RuntimeConfigService.updateConfig(form);
      const hasStoredKey = updated.api_key_masked;
      const formValues = formFromConfig(updated, hasStoredKey);
      set({
        config: updated,
        formValues,
        isDirty: false,
        saving: false,
        successMessage: 'Configuration saved and now active. Changes take effect immediately.',
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save runtime config';
      set({ error: message, saving: false });
    }
  },

  testConnection: async (form) => {
    set({ testing: true, error: null });
    try {
      const result = await RuntimeConfigService.testConnection(form);
      set({
        testing: false,
        testResult: {
          success: result.success,
          message: result.message,
          errorKind: result.error_kind ?? null,
        },
        testTimestamp: Date.now(),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Connection test failed';
      set({
        testing: false,
        testResult: { success: false, message, errorKind: 'unknown' },
        testTimestamp: Date.now(),
      });
    }
  },

  resetConfig: async () => {
    set({ resetting: true, error: null, successMessage: null });
    try {
      const updated = await RuntimeConfigService.resetConfig();
      const hasStoredKey = updated.api_key_masked;
      const formValues = formFromConfig(updated, hasStoredKey);
      set({
        config: updated,
        formValues,
        isDirty: false,
        resetting: false,
        testResult: null,
        testTimestamp: null,
        successMessage: 'Configuration cleared. System now uses default runtime (no custom endpoint).',
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to reset runtime config';
      set({ error: message, resetting: false });
    }
  },

  updateFormValues: (form) => {
    const { config } = get();
    const hasStoredKey = config?.api_key_masked ?? false;
    const savedForm = formFromConfig(config, hasStoredKey);
    set({
      formValues: form,
      isDirty: computeIsDirty(form, savedForm),
    });
  },

  clearMessages: () => set({ error: null, successMessage: null }),
}));
