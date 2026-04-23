import { RuntimeConfigResponse } from '../../core/types/api';

export type RuntimeStatusKind = 'configured' | 'missing_key' | 'disabled' | 'missing';

interface RuntimeStatus {
  kind: RuntimeStatusKind;
  label: string;
  color: string;
  hasUsableKey: boolean;
}

export function deriveRuntimeStatus(config: RuntimeConfigResponse | null): RuntimeStatus {
  if (!config) {
    return { kind: 'missing', label: 'Missing', color: '#f59e0b', hasUsableKey: false };
  }

  if (config.effective_runtime?.api_key_masked) {
    return { kind: 'configured', label: 'Configured', color: '#22c55e', hasUsableKey: true };
  }

  if (config.config_source === 'active_config_env' || config.config_source === 'env_override') {
    return { kind: 'configured', label: 'Configured', color: '#22c55e', hasUsableKey: true };
  }

  if (config.enabled) {
    return { kind: 'missing_key', label: 'Missing API key', color: '#f59e0b', hasUsableKey: false };
  }

  return { kind: 'disabled', label: 'Disabled', color: '#94a3b8', hasUsableKey: false };
}
