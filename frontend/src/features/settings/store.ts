import { create } from 'zustand';
import { RuntimeConfigResponse } from '../../core/types/api';
import { RuntimeConfigService, RuntimeServiceOptions } from '../../lib/api/services/runtime-config';
import { isNetworkError, getErrorMessage } from '../../lib/api/client';

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
  config: RuntimeConfigResponse | null;
  loading: boolean;
  saving: boolean;
  testing: boolean;
  resetting: boolean;
  offline: boolean;          // true when backend unreachable
  configMissing: boolean;    // true when backend online but runtime not configured
  error: string | null;
  successMessage: string | null;
  testResult: TestResult | null;
  testTimestamp: number | null;
  formValues: RuntimeFormValues;
  isDirty: boolean;
  loadConfig: (options?: RuntimeServiceOptions) => Promise<void>;
  saveConfig: (form: RuntimeFormValues, options?: RuntimeServiceOptions) => Promise<void>;
  testConnection: (form: Omit<RuntimeFormValues, 'enabled'>, options?: RuntimeServiceOptions) => Promise<void>;
  resetConfig: (options?: RuntimeServiceOptions) => Promise<void>;
  updateFormValues: (form: RuntimeFormValues) => void;
  clearMessages: () => void;
  setOffline: () => void;
  setOnline: () => void;
}

const DEFAULT_FORM: RuntimeFormValues = {
  provider: 'openai_compatible',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o-mini',
  enabled: false,
};

function formFromConfig(config: RuntimeConfigResponse | null): RuntimeFormValues {
  if (!config) return { ...DEFAULT_FORM };
  return {
    provider: config.provider || DEFAULT_FORM.provider,
    base_url: config.base_url || DEFAULT_FORM.base_url,
    api_key: '',
    model: config.model || DEFAULT_FORM.model,
    enabled: config.enabled,
  };
}

function computeIsDirty(current: RuntimeFormValues, saved: RuntimeFormValues): boolean {
  return (
    current.provider !== saved.provider ||
    current.base_url !== saved.base_url ||
    current.model !== saved.model ||
    current.enabled !== saved.enabled ||
    current.api_key.trim() !== ''
  );
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  config: null,
  loading: false,
  saving: false,
  testing: false,
  resetting: false,
  offline: false,
  configMissing: false,
  error: null,
  successMessage: null,
  testResult: null,
  testTimestamp: null,
  formValues: { ...DEFAULT_FORM },
  isDirty: false,

  setOffline: () => set({ offline: true, configMissing: false, loading: false }),
  setOnline: () => set({ offline: false }),

  loadConfig: async (options) => {
    set({ loading: true, error: null, offline: false });
    try {
      const config = await RuntimeConfigService.getConfig(options);
      const formValues = formFromConfig(config);
      set({
        config,
        formValues,
        isDirty: false,
        loading: false,
        offline: false,
        configMissing: false,
      });
    } catch (err: unknown) {
      if (isNetworkError(err)) {
        // Backend unreachable is an offline state, not a saved configuration error.
        set({ offline: true, loading: false, error: null });
      } else {
        set({ error: getErrorMessage(err, 'Failed to load runtime config'), loading: false, offline: false });
      }
    }
  },

  saveConfig: async (form, options) => {
    set({ saving: true, error: null, successMessage: null });
    try {
      const trimmedApiKey = form.api_key.trim();
      const updated = await RuntimeConfigService.updateConfig({
        provider: form.provider,
        base_url: form.base_url,
        model: form.model,
        enabled: form.enabled,
        ...(trimmedApiKey ? { api_key: trimmedApiKey } : {}),
      }, options);
      const formValues = formFromConfig(updated);
      set({
        config: updated,
        formValues,
        isDirty: false,
        saving: false,
        offline: false,
        successMessage: 'Saved. Runtime changes are active for new runs.',
      });
    } catch (err: unknown) {
      if (isNetworkError(err)) {
        set({ saving: false, offline: true, error: null });
      } else {
        set({ error: getErrorMessage(err, 'Failed to save runtime config'), saving: false });
      }
    }
  },

  testConnection: async (form, options) => {
    set({ testing: true, error: null, testResult: null });
    try {
      const result = await RuntimeConfigService.testConnection({
        ...form,
        api_key: form.api_key.trim(),
      }, options);
      set({
        testing: false,
        testResult: {
          success: result.success,
          message: result.message,
          errorKind: result.error_kind ?? null,
        },
        testTimestamp: Date.now(),
        offline: false,
      });
    } catch (err: unknown) {
      if (isNetworkError(err)) {
        set({
          testing: false,
          testResult: { success: false, message: 'Backend unreachable', errorKind: 'network' },
          testTimestamp: Date.now(),
          offline: true,
        });
      } else {
        set({
          testing: false,
          testResult: {
            success: false,
            message: getErrorMessage(err, 'Connection test failed'),
            errorKind: 'unknown',
          },
          testTimestamp: Date.now(),
        });
      }
    }
  },

  resetConfig: async (options) => {
    set({ resetting: true, error: null, successMessage: null });
    try {
      const updated = await RuntimeConfigService.resetConfig(options);
      const formValues = formFromConfig(updated);
      set({
        config: updated,
        formValues,
        isDirty: false,
        resetting: false,
        testResult: null,
        testTimestamp: null,
        successMessage: 'Cleared. The workspace is using the default runtime again.',
        offline: false,
      });
    } catch (err: unknown) {
      if (isNetworkError(err)) {
        set({ resetting: false, offline: true, error: null });
      } else {
        set({ error: getErrorMessage(err, 'Failed to reset runtime config'), resetting: false });
      }
    }
  },

  updateFormValues: (form) => {
    const savedForm = formFromConfig(get().config);
    set({
      formValues: form,
      isDirty: computeIsDirty(form, savedForm),
      successMessage: null,
      testResult: null,
    });
  },

  clearMessages: () => set({ error: null, successMessage: null }),
}));
