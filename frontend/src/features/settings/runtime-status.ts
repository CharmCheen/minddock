import { RuntimeConfigResponse } from '../../core/types/api';

export type RuntimeStatusKind = 'real_active' | 'unavailable' | 'disabled' | 'missing' | 'mock' | 'fallback';

interface RuntimeStatus {
  kind: RuntimeStatusKind;
  label: string;
  color: string;
  hasUsableKey: boolean;
}

export function deriveRuntimeStatus(config: RuntimeConfigResponse | null): RuntimeStatus {
  if (!config) {
    return { kind: 'missing', label: 'Not configured', color: '#f59e0b', hasUsableKey: false };
  }

  if (config.runtime_status === 'mock') {
    return { kind: 'mock', label: 'Using mock/fallback', color: '#b45309', hasUsableKey: false };
  }

  if (config.runtime_status === 'fallback') {
    return { kind: 'fallback', label: 'Using fallback', color: '#b45309', hasUsableKey: Boolean(config.api_key_configured) };
  }

  if (config.runtime_status === 'connected' || config.config_source === 'active_config_secret' || config.config_source === 'active_config_env' || config.config_source === 'env_override') {
    if (config.api_key_configured || config.effective_runtime?.api_key_masked) {
      return { kind: 'real_active', label: 'Real LLM active', color: '#22c55e', hasUsableKey: true };
    }
  }

  if (config.runtime_status === 'not_configured' || (config.config_source === 'default' && !config.enabled)) {
    return { kind: 'missing', label: 'Not configured', color: '#f59e0b', hasUsableKey: false };
  }

  if (config.enabled || config.runtime_status === 'unavailable') {
    return { kind: 'unavailable', label: 'Configured but unavailable', color: '#f59e0b', hasUsableKey: Boolean(config.api_key_configured) };
  }

  return { kind: 'disabled', label: 'Disabled', color: '#94a3b8', hasUsableKey: false };
}
