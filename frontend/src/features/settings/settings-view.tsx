import React, { useEffect, useState } from 'react';
import { RuntimeFormValues, useSettingsStore } from './store';
import { deriveRuntimeStatus } from './runtime-status';
import { useWorkspacePreferences } from './workspace-preferences';
import { SkillService } from '../../lib/api/services/skills';
import { MediaTranscriptConfigService } from '../../lib/api/services/media-transcript-config';
import {
  MediaTranscriptConfigResponse,
  MediaTranscriptConfigUpdateRequest,
  MediaTranscriptConfigTestResponse,
  LocalAsrStatusResponse,
  LocalAsrModelStatusResponse,
  SourceSkillItem,
  SourceSkillValidationResponse,
} from '../../core/types/api';
import { IconX } from '../../components/ui/icons';

const PROVIDER_LABELS: Record<string, string> = {
  openai_compatible: 'OpenAI-Compatible',
};

const TABS = [
  { id: 'runtime', label: 'Runtime' },
  { id: 'retrieval', label: 'Retrieval' },
  { id: 'display', label: 'Display' },
  { id: 'sources', label: 'Sources' },
] as const;

type TabId = typeof TABS[number]['id'];

const fieldStyle: React.CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  background: 'var(--color-canvas-subtle)',
  border: '1px solid var(--color-border-subtle)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-text-primary)',
  fontSize: '14px',
  boxSizing: 'border-box',
  outline: 'none',
  transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
};

const fieldFocusStyle = {
  borderColor: 'var(--color-brand-200)',
  boxShadow: '0 0 0 3px rgba(59, 130, 246, 0.08)',
};

const tabButtonStyle = (active: boolean): React.CSSProperties => ({
  width: '100%',
  padding: '9px 12px',
  borderRadius: 'var(--radius-md)',
  border: active ? '1px solid var(--color-brand-200)' : '1px solid transparent',
  background: active ? 'var(--color-brand-50)' : 'transparent',
  color: active ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)',
  fontSize: '13px',
  fontWeight: active ? 700 : 500,
  textAlign: 'left',
  cursor: 'pointer',
  transition: 'all var(--transition-fast)',
});


export const SettingsView: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [activeTab, setActiveTab] = useState<TabId>('runtime');
  const { density } = useWorkspacePreferences();

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
      className="animate-fade-in"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.35)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        animation: 'fadeIn 150ms ease forwards',
      }}
    >
      <div
        style={{
          width: '760px',
          maxWidth: '96vw',
          maxHeight: '92vh',
          height: '92vh',
          overflow: 'hidden',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-xl)',
          color: 'var(--color-text-primary)',
          display: 'flex',
          animation: 'scaleIn 200ms ease forwards',
        }}
      >
        <aside style={{
          width: '200px',
          flexShrink: 0,
          borderRight: '1px solid var(--color-border-subtle)',
          background: 'var(--color-canvas-subtle)',
          padding: density === 'compact' ? '14px' : '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          overflowY: 'auto',
        }}>
          <h2 id="settings-title" style={{ margin: '0 0 14px', fontSize: '16px', fontWeight: 700, color: 'var(--color-text-primary)' }}>
            Settings
          </h2>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              style={tabButtonStyle(activeTab === tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </aside>

        <section style={{ padding: density === 'compact' ? '18px' : '22px', overflowY: 'auto', minHeight: 0, flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', marginBottom: '18px' }}>
            <div>
              <h3 style={{ margin: '0 0 5px', fontSize: '18px', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                {activeTab === 'runtime' && 'Models & Runtime'}
                {activeTab === 'retrieval' && 'Retrieval'}
                {activeTab === 'display' && 'Display'}
                {activeTab === 'sources' && 'Source Skills'}
              </h3>
              <p style={{ margin: 0, color: 'var(--color-text-tertiary)', fontSize: '13px' }}>
                {activeTab === 'runtime' && 'Configure the OpenAI-compatible endpoint used by model-backed runs.'}
                {activeTab === 'retrieval' && 'Default parameters for source retrieval and citation.'}
                {activeTab === 'display' && 'UI preferences stored locally in your browser.'}
                {activeTab === 'sources' && 'Supported source types and their limitations.'}
              </p>
            </div>
            <button
              type="button"
              aria-label="Close settings"
              onClick={onClose}
              style={{
                width: '32px',
                height: '32px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border-subtle)',
                background: 'var(--color-canvas-subtle)',
                color: 'var(--color-text-tertiary)',
                cursor: 'pointer',
                fontSize: '18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                lineHeight: 1,
                transition: 'all var(--transition-fast)',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.background = 'var(--color-canvas)';
                e.currentTarget.style.color = 'var(--color-text-secondary)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = 'var(--color-canvas-subtle)';
                e.currentTarget.style.color = 'var(--color-text-tertiary)';
              }}
            >
              <IconX size={18} />
            </button>
          </div>

          {activeTab === 'runtime' && <RuntimeTab />}
          {activeTab === 'retrieval' && <RetrievalTab />}
          {activeTab === 'display' && <DisplayTab />}
          {activeTab === 'sources' && <SourcesTab />}
        </section>
      </div>
    </div>
  );
};

function RuntimeTab() {
  const {
    config,
    formValues,
    loading,
    saving,
    testing,
    resetting,
    error,
    successMessage,
    testResult,
    isDirty,
    loadConfig,
    saveConfig,
    testConnection,
    resetConfig,
    updateFormValues,
  } = useSettingsStore();

  const [form, setForm] = useState<RuntimeFormValues>(formValues);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    setForm(formValues);
  }, [formValues]);

  const patchForm = (patch: Partial<RuntimeFormValues>) => {
    const next = { ...form, ...patch };
    setForm(next);
    updateFormValues(next);
  };

  const status = deriveRuntimeStatus(config);
  const effectiveRuntime = config?.effective_runtime;
  const effectiveProviderLabel = PROVIDER_LABELS[effectiveRuntime?.provider_kind || ''] || effectiveRuntime?.provider_kind || 'Not configured';
  const hasUsableKey = status.hasUsableKey;
  const canSave = isDirty && !saving;
  const canTest = Boolean(form.base_url.trim() && form.model.trim()) && !testing;

  const handleSave = () => {
    void saveConfig(form);
  };

  const handleTest = () => {
    void testConnection({
      provider: form.provider,
      base_url: form.base_url,
      api_key: form.api_key,
      model: form.model,
    });
  };

  return (
    <>
      <div
        data-testid="runtime-current-status"
        style={{
          padding: '14px',
          background: 'var(--color-canvas-subtle)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-md)',
          display: 'grid',
          gap: '10px',
          marginBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Effective Runtime
          </span>
          <span
            style={{
              padding: '3px 10px',
              borderRadius: 'var(--radius-full)',
              background: `${status.color}15`,
              border: `1px solid ${status.color}40`,
              color: status.color,
              fontSize: '11px',
              fontWeight: 700,
            }}
          >
            {successMessage ? 'Saved' : error ? 'Error' : status.label}
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '5px 10px', fontSize: '13px' }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>Provider Type</span>
          <span style={{ color: 'var(--color-text-primary)', fontWeight: 500 }}>{effectiveProviderLabel}</span>
          <span style={{ color: 'var(--color-text-tertiary)' }}>Base URL</span>
          <span style={{ fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere', color: 'var(--color-text-secondary)' }}>{effectiveRuntime?.base_url || 'Not configured'}</span>
          <span style={{ color: 'var(--color-text-tertiary)' }}>Model</span>
          <span style={{ color: 'var(--color-text-primary)', fontWeight: 500 }}>{effectiveRuntime?.model_name || 'Not configured'}</span>
          <span style={{ color: 'var(--color-text-tertiary)' }}>Profile</span>
          <span style={{ color: 'var(--color-text-secondary)' }}>{effectiveRuntime?.profile_id || 'Not configured'}</span>
          <span style={{ color: 'var(--color-text-tertiary)' }}>API Key</span>
          <span style={{ color: 'var(--color-text-secondary)' }}>{hasUsableKey ? '********' : 'Not configured'}</span>
        </div>
      </div>

      {!loading && status.kind === 'missing_key' && (
        <div
          style={{
            marginBottom: '14px',
            padding: '10px 14px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-warning-bg)',
            border: '1px solid var(--color-warning-border)',
            color: 'var(--color-warning-text)',
            fontSize: '13px',
            fontWeight: 500,
          }}
        >
          Runtime is missing an API key. Add one here before running model-backed tasks.
        </div>
      )}

      {loading ? (
        <p style={{ color: 'var(--color-text-tertiary)', fontSize: '14px' }}>Loading runtime settings...</p>
      ) : (
        <form
          data-testid="runtime-settings-form"
          onSubmit={(event) => {
            event.preventDefault();
            handleSave();
          }}
          style={{ display: 'grid', gap: '14px' }}
        >
          <div style={{ color: 'var(--color-text-tertiary)', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Saved Runtime Config
          </div>

          <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
            Provider Type
            <select
              value={form.provider}
              disabled
              onChange={(event) => patchForm({ provider: event.target.value })}
              style={{ ...fieldStyle, color: 'var(--color-text-tertiary)' }}
            >
              <option value="openai_compatible">OpenAI-Compatible</option>
            </select>
          </label>

          <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
            Base URL
            <input
              data-testid="runtime-base-url"
              value={form.base_url}
              onChange={(event) => patchForm({ base_url: event.target.value })}
              placeholder="https://api.openai.com/v1"
              style={fieldStyle}
              onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--color-border-subtle)';
                e.target.style.boxShadow = 'none';
              }}
            />
          </label>

          <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
            API Key
            <input
              data-testid="runtime-api-key"
              type="password"
              value={form.api_key}
              onChange={(event) => patchForm({ api_key: event.target.value })}
              placeholder={hasUsableKey ? 'Configured - leave blank to keep current key' : 'Enter API key'}
              autoComplete="off"
              style={fieldStyle}
              onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--color-border-subtle)';
                e.target.style.boxShadow = 'none';
              }}
            />
            <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', lineHeight: 1.45 }}>
              API key is kept only for the current backend session. After restarting the backend, re-enter it or set LLM_API_KEY in your environment.
            </span>
          </label>

          <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
            Model
            <input
              data-testid="runtime-model"
              value={form.model}
              onChange={(event) => patchForm({ model: event.target.value })}
              placeholder="gpt-4o-mini"
              style={fieldStyle}
              onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--color-border-subtle)';
                e.target.style.boxShadow = 'none';
              }}
            />
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-text-secondary)', fontSize: '14px', fontWeight: 500 }}>
            <input
              data-testid="runtime-enabled"
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => patchForm({ enabled: event.target.checked })}
            />
            Enable this runtime for new runs
          </label>

          {testResult && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 'var(--radius-md)',
                background: testResult.success ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                border: `1px solid ${testResult.success ? 'var(--color-success-border)' : 'var(--color-error-border)'}`,
                color: testResult.success ? 'var(--color-success-text)' : 'var(--color-error-text)',
                fontSize: '13px',
              }}
            >
              <strong>{testResult.success ? 'Connection OK' : 'Connection failed'}</strong>
              <div style={{ marginTop: '3px' }}>{testResult.message}</div>
            </div>
          )}

          {error && (
            <div style={{
              padding: '10px 14px',
              background: 'var(--color-error-bg)',
              border: '1px solid var(--color-error-border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-error-text)',
              fontSize: '13px',
            }}>
              {error}
            </div>
          )}
          {successMessage && (
            <div style={{
              padding: '10px 14px',
              background: 'var(--color-success-bg)',
              border: '1px solid var(--color-success-border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-success-text)',
              fontSize: '13px',
            }}>
              {successMessage}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginTop: '4px' }}>
            <button
              type="button"
              onClick={() => void resetConfig()}
              disabled={resetting}
              style={{
                padding: '9px 14px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-error-border)',
                background: 'var(--color-error-bg)',
                color: 'var(--color-error-text)',
                cursor: resetting ? 'not-allowed' : 'pointer',
                fontWeight: 600,
                fontSize: '13px',
                transition: 'all var(--transition-fast)',
              }}
            >
              {resetting ? 'Resetting...' : 'Reset'}
            </button>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="button"
                onClick={handleTest}
                disabled={!canTest}
                style={{
                  padding: '9px 14px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--color-border-subtle)',
                  background: 'var(--color-canvas-subtle)',
                  color: 'var(--color-text-secondary)',
                  cursor: canTest ? 'pointer' : 'not-allowed',
                  opacity: canTest ? 1 : 0.55,
                  fontWeight: 600,
                  fontSize: '13px',
                  transition: 'all var(--transition-fast)',
                }}
              >
                {testing ? 'Testing...' : 'Test Connection'}
              </button>
              <button
                type="submit"
                data-testid="runtime-save"
                disabled={!canSave}
                style={{
                  padding: '9px 18px',
                  borderRadius: 'var(--radius-md)',
                  border: 'none',
                  background: !canSave ? 'var(--color-canvas)' : 'var(--color-brand-600)',
                  color: !canSave ? 'var(--color-text-tertiary)' : '#fff',
                  fontWeight: 700,
                  cursor: canSave ? 'pointer' : 'not-allowed',
                  opacity: canSave ? 1 : 0.55,
                  fontSize: '13px',
                  transition: 'all var(--transition-fast)',
                  boxShadow: canSave ? 'var(--shadow-md)' : 'none',
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </form>
      )}

      <MediaTranscriptEditor />
    </>
  );
}

interface MediaTranscriptFormValues {
  provider: 'mock' | 'api' | 'local' | 'disabled';
  enabled: boolean;
  base_url: string;
  api_key: string;
  model: string;
  timeout_seconds: number;
  local_asr_server_path: string;
  local_asr_host: string;
  local_asr_port: number;
  local_asr_model: string;
  local_asr_device: string;
  local_asr_compute_type: string;
  local_asr_auto_start: boolean;
  local_asr_timeout_seconds: number;
}

function MediaTranscriptEditor() {
  const [config, setConfig] = useState<MediaTranscriptConfigResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<MediaTranscriptConfigTestResponse | null>(null);
  const [localAsrStatus, setLocalAsrStatus] = useState<LocalAsrStatusResponse | null>(null);
  const [checkingLocalAsr, setCheckingLocalAsr] = useState(false);
  const [startingLocalAsr, setStartingLocalAsr] = useState(false);
  const [localModelStatus, setLocalModelStatus] = useState<LocalAsrModelStatusResponse | null>(null);
  const [checkingLocalModel, setCheckingLocalModel] = useState(false);
  const [preloadingLocalModel, setPreloadingLocalModel] = useState(false);

  const [form, setForm] = useState<MediaTranscriptFormValues>({
    provider: 'mock',
    enabled: false,
    base_url: '',
    api_key: '',
    model: 'whisper-1',
    timeout_seconds: 60,
    local_asr_server_path: 'D:\\大学\\毕业设计\\code\\local_asr_server',
    local_asr_host: '127.0.0.1',
    local_asr_port: 9001,
    local_asr_model: 'small',
    local_asr_device: 'auto',
    local_asr_compute_type: 'int8',
    local_asr_auto_start: true,
    local_asr_timeout_seconds: 120,
  });

  const loadConfig = () => {
    let cancelled = false;
    setLoading(true);
    MediaTranscriptConfigService.getConfig()
      .then((data) => {
        if (cancelled) return;
        setConfig(data);
        setForm({
          provider: (data.provider as MediaTranscriptFormValues['provider']) || 'mock',
          enabled: data.enabled,
          base_url: data.base_url ?? '',
          api_key: '',
          model: data.model || 'whisper-1',
          timeout_seconds: data.timeout_seconds || 60,
          local_asr_server_path: data.local_asr_server_path || 'D:\\大学\\毕业设计\\code\\local_asr_server',
          local_asr_host: data.local_asr_host || '127.0.0.1',
          local_asr_port: data.local_asr_port || 9001,
          local_asr_model: data.local_asr_model || 'small',
          local_asr_device: data.local_asr_device || 'auto',
          local_asr_compute_type: data.local_asr_compute_type || 'int8',
          local_asr_auto_start: data.local_asr_auto_start ?? true,
          local_asr_timeout_seconds: data.local_asr_timeout_seconds || 120,
        });
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  };

  useEffect(() => {
    const cleanup = loadConfig();
    return cleanup;
  }, []);

  const patchForm = (patch: Partial<MediaTranscriptFormValues>) => {
    setForm((prev) => ({ ...prev, ...patch }));
    setSuccessMessage(null);
    setTestResult(null);
    setLocalAsrStatus(null);
    setLocalModelStatus(null);
  };

  const handleCheckLocalAsr = async () => {
    setCheckingLocalAsr(true);
    setError(null);
    setLocalAsrStatus(null);
    try {
      const result = await MediaTranscriptConfigService.checkLocalStatus();
      setLocalAsrStatus(result);
    } catch (err: unknown) {
      setLocalAsrStatus({
        status: 'failed',
        provider: form.provider,
        enabled: form.enabled,
        base_url: '',
        health_url: '',
        model: form.local_asr_model,
        message: err instanceof Error ? err.message : 'Status check failed.',
      });
    } finally {
      setCheckingLocalAsr(false);
    }
  };

  const handleStartLocalAsr = async () => {
    setStartingLocalAsr(true);
    setError(null);
    setLocalAsrStatus(null);
    try {
      const result = await MediaTranscriptConfigService.startLocalAsr();
      setLocalAsrStatus(result);
    } catch (err: unknown) {
      setLocalAsrStatus({
        status: 'failed',
        provider: form.provider,
        enabled: form.enabled,
        base_url: '',
        health_url: '',
        model: form.local_asr_model,
        message: err instanceof Error ? err.message : 'Start request failed.',
      });
    } finally {
      setStartingLocalAsr(false);
    }
  };

  const handleCheckLocalModel = async () => {
    setCheckingLocalModel(true);
    setError(null);
    setLocalModelStatus(null);
    try {
      const result = await MediaTranscriptConfigService.checkLocalModelStatus();
      setLocalModelStatus(result);
    } catch (err: unknown) {
      setLocalModelStatus({
        status: 'failed',
        model: form.local_asr_model,
        message: err instanceof Error ? err.message : 'Model status check failed.',
      });
    } finally {
      setCheckingLocalModel(false);
    }
  };

  const handlePreloadLocalModel = async () => {
    setPreloadingLocalModel(true);
    setError(null);
    setLocalModelStatus(null);
    try {
      const result = await MediaTranscriptConfigService.preloadLocalModel();
      setLocalModelStatus(result);
    } catch (err: unknown) {
      setLocalModelStatus({
        status: 'failed',
        model: form.local_asr_model,
        message: err instanceof Error ? err.message : 'Model preload failed.',
      });
    } finally {
      setPreloadingLocalModel(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const trimmedKey = form.api_key.trim();
      const payload: MediaTranscriptConfigUpdateRequest = {
        provider: form.provider,
        enabled: form.enabled,
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        timeout_seconds: form.timeout_seconds,
        local_asr_server_path: form.local_asr_server_path.trim(),
        local_asr_host: form.local_asr_host.trim(),
        local_asr_port: form.local_asr_port,
        local_asr_model: form.local_asr_model.trim(),
        local_asr_device: form.local_asr_device.trim(),
        local_asr_compute_type: form.local_asr_compute_type.trim(),
        local_asr_auto_start: form.local_asr_auto_start,
        local_asr_timeout_seconds: form.local_asr_timeout_seconds,
      };
      if (trimmedKey) {
        payload.api_key = trimmedKey;
      }
      await MediaTranscriptConfigService.updateConfig(payload);
      setForm((prev) => ({ ...prev, api_key: '' }));
      loadConfig();
      setSuccessMessage('Configuration saved.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save media transcript config.');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await MediaTranscriptConfigService.resetConfig();
      setForm((prev) => ({ ...prev, api_key: '' }));
      loadConfig();
      setSuccessMessage('Configuration reset to defaults.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reset media transcript config.');
    } finally {
      setResetting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const trimmedKey = form.api_key.trim();
      const payload: MediaTranscriptConfigUpdateRequest = {
        provider: form.provider,
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        local_asr_server_path: form.local_asr_server_path.trim(),
        local_asr_host: form.local_asr_host.trim(),
        local_asr_port: form.local_asr_port,
        local_asr_model: form.local_asr_model.trim(),
        local_asr_device: form.local_asr_device.trim(),
        local_asr_compute_type: form.local_asr_compute_type.trim(),
        local_asr_auto_start: form.local_asr_auto_start,
        local_asr_timeout_seconds: form.local_asr_timeout_seconds,
      };
      if (trimmedKey) {
        payload.api_key = trimmedKey;
      }
      const result = await MediaTranscriptConfigService.testConfig(payload);
      setTestResult(result);
    } catch (err: unknown) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : 'Test request failed.',
      });
    } finally {
      setTesting(false);
    }
  };

  const isLocal = form.provider === 'local';
  const isApi = form.provider === 'api';

  const statusColor = config?.enabled
    ? (isLocal ? '#22c55e' : config?.api_key_configured ? '#22c55e' : '#f59e0b')
    : '#94a3b8';
  const statusLabel = config?.enabled
    ? (isLocal ? 'Enabled' : config?.api_key_configured ? 'Enabled' : 'Enabled — missing key')
    : 'Disabled';

  const canTest = form.provider === 'mock'
    || form.provider === 'disabled'
    || (isApi && Boolean(form.base_url.trim() && form.model.trim()))
    || (isLocal && Boolean(form.local_asr_server_path.trim() && form.local_asr_model.trim()));

  return (
    <div
      data-testid="media-transcript-status"
      style={{
        padding: '14px',
        background: 'var(--color-canvas-subtle)',
        border: '1px solid var(--color-border-subtle)',
        borderRadius: 'var(--radius-md)',
        display: 'grid',
        gap: '10px',
        marginTop: '16px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Media Transcript Provider
        </span>
        <span
          style={{
            padding: '3px 10px',
            borderRadius: 'var(--radius-full)',
            background: `${statusColor}15`,
            border: `1px solid ${statusColor}40`,
            color: statusColor,
            fontSize: '11px',
            fontWeight: 700,
          }}
        >
          {loading ? 'Loading…' : statusLabel}
        </span>
      </div>

      <div
        style={{
          padding: '10px 12px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '12px',
          color: 'var(--color-text-tertiary)',
          lineHeight: 1.45,
        }}
      >
        Used during media ingestion to turn audio/video files into transcript text.
        This does not perform frame-level video understanding.
      </div>

      {loading ? (
        <p style={{ color: 'var(--color-text-tertiary)', fontSize: '14px', margin: 0 }}>Loading media transcript settings...</p>
      ) : (
        <form
          data-testid="media-transcript-form"
          onSubmit={(e) => { e.preventDefault(); void handleSave(); }}
          style={{ display: 'grid', gap: '12px' }}
        >
          <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
            Provider
            <select
              value={form.provider}
              onChange={(e) => patchForm({ provider: e.target.value as MediaTranscriptFormValues['provider'] })}
              style={fieldStyle}
            >
              <option value="mock">Mock (transcript passthrough)</option>
              <option value="api">Remote API (OpenAI-compatible ASR)</option>
              <option value="local">Local ASR</option>
              <option value="disabled">Disabled</option>
            </select>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-text-secondary)', fontSize: '14px', fontWeight: 500 }}>
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => patchForm({ enabled: e.target.checked })}
            />
            Enable media transcript provider
          </label>

          {isApi && (
            <>
              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                API Base URL
                <input
                  value={form.base_url}
                  onChange={(e) => patchForm({ base_url: e.target.value })}
                  placeholder={config?.base_url_configured ? 'Configured — enter new URL to change' : 'https://api.example.com/v1'}
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                API Key
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => patchForm({ api_key: e.target.value })}
                  placeholder={config?.api_key_configured ? 'Configured — leave blank to keep current key' : 'Enter API key'}
                  autoComplete="off"
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
                <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', lineHeight: 1.45 }}>
                  API key is kept only for the current backend session and is not written to disk.
                </span>
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Model
                <input
                  value={form.model}
                  onChange={(e) => patchForm({ model: e.target.value })}
                  placeholder="whisper-1"
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Timeout (seconds)
                <input
                  type="number"
                  min={1}
                  max={600}
                  value={form.timeout_seconds}
                  onChange={(e) => patchForm({ timeout_seconds: Math.max(1, Math.min(600, Number(e.target.value) || 60)) })}
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>
            </>
          )}

          {isLocal && (
            <>
              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Local ASR Server Path
                <input
                  value={form.local_asr_server_path}
                  onChange={(e) => patchForm({ local_asr_server_path: e.target.value })}
                  placeholder={'D:\\大学\\毕业设计\\code\\local_asr_server'}
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Host
                <input
                  value={form.local_asr_host}
                  onChange={(e) => patchForm({ local_asr_host: e.target.value })}
                  placeholder="127.0.0.1"
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Port
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={form.local_asr_port}
                  onChange={(e) => patchForm({ local_asr_port: Math.max(1, Math.min(65535, Number(e.target.value) || 9001)) })}
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Model
                <select
                  value={form.local_asr_model}
                  onChange={(e) => patchForm({ local_asr_model: e.target.value })}
                  style={fieldStyle}
                >
                  <option value="tiny">tiny</option>
                  <option value="base">base</option>
                  <option value="small">small</option>
                  <option value="medium">medium</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Device
                <select
                  value={form.local_asr_device}
                  onChange={(e) => patchForm({ local_asr_device: e.target.value })}
                  style={fieldStyle}
                >
                  <option value="auto">auto</option>
                  <option value="cuda">cuda</option>
                  <option value="cpu">cpu</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Compute Type
                <select
                  value={form.local_asr_compute_type}
                  onChange={(e) => patchForm({ local_asr_compute_type: e.target.value })}
                  style={fieldStyle}
                >
                  <option value="int8">int8</option>
                </select>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-text-secondary)', fontSize: '14px', fontWeight: 500 }}>
                <input
                  type="checkbox"
                  checked={form.local_asr_auto_start}
                  onChange={(e) => patchForm({ local_asr_auto_start: e.target.checked })}
                />
                Auto-start local ASR server
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
                Timeout (seconds)
                <input
                  type="number"
                  min={1}
                  max={600}
                  value={form.local_asr_timeout_seconds}
                  onChange={(e) => patchForm({ local_asr_timeout_seconds: Math.max(1, Math.min(600, Number(e.target.value) || 120)) })}
                  style={fieldStyle}
                  onFocus={(e) => Object.assign(e.target.style, fieldFocusStyle)}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--color-border-subtle)'; e.target.style.boxShadow = 'none'; }}
                />
              </label>

              <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', lineHeight: 1.5, padding: '6px 0' }}>
                Local ASR runs a local OpenAI-compatible transcription service managed by MindDock.
                It transcribes audio only and does not perform frame-level video understanding.
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => void handleCheckLocalAsr()}
                  disabled={checkingLocalAsr}
                  style={{
                    padding: '9px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--color-border-subtle)',
                    background: 'var(--color-canvas-subtle)',
                    color: 'var(--color-text-secondary)',
                    cursor: checkingLocalAsr ? 'not-allowed' : 'pointer',
                    opacity: checkingLocalAsr ? 0.55 : 1,
                    fontWeight: 600,
                    fontSize: '13px',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  {checkingLocalAsr ? 'Checking…' : 'Check Status'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleStartLocalAsr()}
                  disabled={startingLocalAsr}
                  style={{
                    padding: '9px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: 'none',
                    background: startingLocalAsr ? 'var(--color-canvas)' : 'var(--color-brand-600)',
                    color: startingLocalAsr ? 'var(--color-text-tertiary)' : '#fff',
                    cursor: startingLocalAsr ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    fontSize: '13px',
                    transition: 'all var(--transition-fast)',
                    boxShadow: startingLocalAsr ? 'none' : 'var(--shadow-md)',
                  }}
                >
                  {startingLocalAsr ? 'Starting…' : 'Start Local ASR'}
                </button>
              </div>

              {localAsrStatus && (
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: 'var(--radius-md)',
                    background: ['connected', 'already_running', 'started'].includes(localAsrStatus.status)
                      ? 'var(--color-success-bg)'
                      : 'var(--color-error-bg)',
                    border: `1px solid ${['connected', 'already_running', 'started'].includes(localAsrStatus.status)
                      ? 'var(--color-success-border)'
                      : 'var(--color-error-border)'}`,
                    color: ['connected', 'already_running', 'started'].includes(localAsrStatus.status)
                      ? 'var(--color-success-text)'
                      : 'var(--color-error-text)',
                    fontSize: '13px',
                  }}
                >
                  <strong>
                    {localAsrStatus.status === 'connected' && 'Connected'}
                    {localAsrStatus.status === 'already_running' && 'Already Running'}
                    {localAsrStatus.status === 'started' && 'Started'}
                    {localAsrStatus.status === 'not_running' && 'Not Running'}
                    {localAsrStatus.status === 'not_configured' && 'Not Configured'}
                    {localAsrStatus.status === 'not_local_provider' && 'Not Local Provider'}
                    {localAsrStatus.status === 'failed' && 'Failed'}
                    {!['connected', 'already_running', 'started', 'not_running', 'not_configured', 'not_local_provider', 'failed'].includes(localAsrStatus.status) && localAsrStatus.status}
                  </strong>
                  <div style={{ marginTop: '3px' }}>{localAsrStatus.message}</div>
                  {localAsrStatus.base_url && (
                    <div style={{ marginTop: '3px', fontSize: '11px', opacity: 0.85 }}>
                      Base URL: {localAsrStatus.base_url}
                    </div>
                  )}
                  {localAsrStatus.model && (
                    <div style={{ fontSize: '11px', opacity: 0.85 }}>
                      Model: {localAsrStatus.model}
                    </div>
                  )}
                </div>
              )}

              <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', lineHeight: 1.5, padding: '6px 0' }}>
                <strong>Recommended flow:</strong><br />
                1. Save settings<br />
                2. Start Local ASR<br />
                3. Check Status<br />
                4. Preload Model<br />
                5. Wait until Ready<br />
                6. Run ingest<br />
                <em>Save changes before checking or preloading the model.</em>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => void handleCheckLocalModel()}
                  disabled={checkingLocalModel}
                  style={{
                    padding: '9px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--color-border-subtle)',
                    background: 'var(--color-canvas-subtle)',
                    color: 'var(--color-text-secondary)',
                    cursor: checkingLocalModel ? 'not-allowed' : 'pointer',
                    opacity: checkingLocalModel ? 0.55 : 1,
                    fontWeight: 600,
                    fontSize: '13px',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  {checkingLocalModel ? 'Checking…' : 'Check Model'}
                </button>
                <button
                  type="button"
                  onClick={() => void handlePreloadLocalModel()}
                  disabled={preloadingLocalModel}
                  style={{
                    padding: '9px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: 'none',
                    background: preloadingLocalModel ? 'var(--color-canvas)' : 'var(--color-brand-600)',
                    color: preloadingLocalModel ? 'var(--color-text-tertiary)' : '#fff',
                    cursor: preloadingLocalModel ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    fontSize: '13px',
                    transition: 'all var(--transition-fast)',
                    boxShadow: preloadingLocalModel ? 'none' : 'var(--shadow-md)',
                  }}
                >
                  {preloadingLocalModel ? 'Preloading…' : 'Preload Model'}
                </button>
              </div>

              {localModelStatus && (
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: 'var(--radius-md)',
                    background: localModelStatus.status === 'ready'
                      ? 'var(--color-success-bg)'
                      : localModelStatus.status === 'loading'
                        ? 'var(--color-warning-bg)'
                        : 'var(--color-error-bg)',
                    border: `1px solid ${localModelStatus.status === 'ready'
                      ? 'var(--color-success-border)'
                      : localModelStatus.status === 'loading'
                        ? 'var(--color-warning-border)'
                        : 'var(--color-error-border)'}`,
                    color: localModelStatus.status === 'ready'
                      ? 'var(--color-success-text)'
                      : localModelStatus.status === 'loading'
                        ? 'var(--color-warning-text)'
                        : 'var(--color-error-text)',
                    fontSize: '13px',
                  }}
                >
                  <strong>
                    {localModelStatus.status === 'ready' && 'Ready'}
                    {localModelStatus.status === 'loading' && 'Loading'}
                    {localModelStatus.status === 'not_loaded' && 'Not Loaded'}
                    {localModelStatus.status === 'failed' && 'Failed'}
                    {localModelStatus.status === 'not_running' && 'Server Not Running'}
                    {localModelStatus.status === 'not_configured' && 'Not Configured'}
                    {localModelStatus.status === 'not_local_provider' && 'Not Local Provider'}
                    {!['ready', 'loading', 'not_loaded', 'failed', 'not_running', 'not_configured', 'not_local_provider'].includes(localModelStatus.status) && localModelStatus.status}
                  </strong>
                  <div style={{ marginTop: '3px' }}>{localModelStatus.message}</div>
                  {localModelStatus.model && (
                    <div style={{ marginTop: '3px', fontSize: '11px', opacity: 0.85 }}>
                      Model: {localModelStatus.model}
                    </div>
                  )}
                  {localModelStatus.requested_device && (
                    <div style={{ fontSize: '11px', opacity: 0.85 }}>
                      Device: {localModelStatus.requested_device}
                      {localModelStatus.actual_device && localModelStatus.actual_device !== localModelStatus.requested_device
                        ? ` → ${localModelStatus.actual_device}` : ''}
                    </div>
                  )}
                  {localModelStatus.compute_type && (
                    <div style={{ fontSize: '11px', opacity: 0.85 }}>
                      Compute Type: {localModelStatus.compute_type}
                    </div>
                  )}
                  {localModelStatus.base_url && (
                    <div style={{ fontSize: '11px', opacity: 0.85 }}>
                      Base URL: {localModelStatus.base_url}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {config && (
            <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '4px 10px', fontSize: '12px', padding: '8px 0', borderTop: '1px solid var(--color-border-subtle)' }}>
              <span style={{ color: 'var(--color-text-tertiary)' }}>API Key</span>
              <span style={{ color: config.api_key_configured ? 'var(--color-success-text)' : 'var(--color-warning-text)' }}>
                {config.api_key_configured ? 'Configured' : 'Missing'}
              </span>

              <span style={{ color: 'var(--color-text-tertiary)' }}>Base URL</span>
              <span style={{ color: config.base_url_configured ? 'var(--color-success-text)' : 'var(--color-warning-text)' }}>
                {config.base_url_configured ? 'Configured' : 'Missing'}
              </span>

              <span style={{ color: 'var(--color-text-tertiary)' }}>Config source</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {config.config_source === 'ui_override' ? 'UI override' : 'Environment variables'}
              </span>

              <span style={{ color: 'var(--color-text-tertiary)' }}>Capability</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>Transcript-only ASR</span>

              <span style={{ color: 'var(--color-text-tertiary)' }}>Limitations</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {config.limitations.map((l) => l.replace(/_/g, ' ')).join(', ')}
              </span>
            </div>
          )}

          {!isLocal && (
            <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', lineHeight: 1.5, padding: '6px 0' }}>
              Provider, base URL, model and timeout may persist as non-secret configuration.
              Saved UI configuration is now used by media ingestion. Sidecar transcripts still take precedence over API transcription.
              Reset clears the UI override and current backend-session key. If you rely on shell environment variables, restart the backend or reconfigure as needed.
            </div>
          )}

          {testResult && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 'var(--radius-md)',
                background: testResult.success ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                border: `1px solid ${testResult.success ? 'var(--color-success-border)' : 'var(--color-error-border)'}`,
                color: testResult.success ? 'var(--color-success-text)' : 'var(--color-error-text)',
                fontSize: '13px',
              }}
            >
              <strong>{testResult.success ? 'Config OK' : 'Config incomplete'}</strong>
              <div style={{ marginTop: '3px' }}>{testResult.message}</div>
            </div>
          )}

          {error && (
            <div style={{ padding: '10px 14px', background: 'var(--color-error-bg)', border: '1px solid var(--color-error-border)', borderRadius: 'var(--radius-md)', color: 'var(--color-error-text)', fontSize: '13px' }}>
              {error}
            </div>
          )}
          {successMessage && (
            <div style={{ padding: '10px 14px', background: 'var(--color-success-bg)', border: '1px solid var(--color-success-border)', borderRadius: 'var(--radius-md)', color: 'var(--color-success-text)', fontSize: '13px' }}>
              {successMessage}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginTop: '4px' }}>
            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={resetting}
              style={{
                padding: '9px 14px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-error-border)',
                background: 'var(--color-error-bg)',
                color: 'var(--color-error-text)',
                cursor: resetting ? 'not-allowed' : 'pointer',
                fontWeight: 600,
                fontSize: '13px',
                transition: 'all var(--transition-fast)',
              }}
            >
              {resetting ? 'Resetting...' : 'Reset'}
            </button>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="button"
                onClick={() => void handleTest()}
                disabled={!canTest || testing}
                style={{
                  padding: '9px 14px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--color-border-subtle)',
                  background: 'var(--color-canvas-subtle)',
                  color: 'var(--color-text-secondary)',
                  cursor: canTest && !testing ? 'pointer' : 'not-allowed',
                  opacity: canTest && !testing ? 1 : 0.55,
                  fontWeight: 600,
                  fontSize: '13px',
                  transition: 'all var(--transition-fast)',
                }}
              >
                {testing ? 'Testing...' : 'Test Config'}
              </button>
              <button
                type="submit"
                disabled={saving}
                style={{
                  padding: '9px 18px',
                  borderRadius: 'var(--radius-md)',
                  border: 'none',
                  background: saving ? 'var(--color-canvas)' : 'var(--color-brand-600)',
                  color: saving ? 'var(--color-text-tertiary)' : '#fff',
                  fontWeight: 700,
                  cursor: saving ? 'not-allowed' : 'pointer',
                  fontSize: '13px',
                  transition: 'all var(--transition-fast)',
                  boxShadow: saving ? 'none' : 'var(--shadow-md)',
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}

function RetrievalTab() {
  const {
    defaultTopK,
    defaultCitationPolicy,
    defaultSummarizeMode,
    setDefaultTopK,
    setDefaultCitationPolicy,
    setDefaultSummarizeMode,
    density,
  } = useWorkspacePreferences();

  return (
    <div style={{ display: 'grid', gap: density === 'compact' ? '14px' : '18px' }}>
      <div style={{
        padding: '12px 14px',
        background: 'var(--color-canvas-subtle)',
        border: '1px solid var(--color-border-subtle)',
        borderRadius: 'var(--radius-md)',
        fontSize: '13px',
        color: 'var(--color-text-tertiary)',
      }}>
        These settings affect the next request. They do not change the index or embedding model.
      </div>

      <label style={{ display: 'grid', gap: '6px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
        Default top_k (retrieval depth)
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <input
            type="range"
            min={1}
            max={20}
            value={defaultTopK}
            onChange={(e) => setDefaultTopK(Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ color: 'var(--color-text-primary)', fontSize: '14px', fontWeight: 700, minWidth: '28px', textAlign: 'center' }}>
            {defaultTopK}
          </span>
        </div>
        <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>
          How many chunks to retrieve before ranking and generating an answer.
        </span>
      </label>

      <label style={{ display: 'grid', gap: '6px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
        Citation policy
        <select
          value={defaultCitationPolicy}
          onChange={(e) => setDefaultCitationPolicy(e.target.value as 'required' | 'preferred' | 'none')}
          style={fieldStyle}
        >
          <option value="preferred">Preferred 鈥?cite when evidence exists</option>
          <option value="required">Required 鈥?refuse if no evidence</option>
          <option value="none">None 鈥?do not include citations</option>
        </select>
        <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>
          Whether answers must include verifiable source citations.
        </span>
      </label>

      <label style={{ display: 'grid', gap: '6px', fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>
        Summarize mode
        <select
          value={defaultSummarizeMode}
          onChange={(e) => setDefaultSummarizeMode(e.target.value as 'basic' | 'map_reduce')}
          style={fieldStyle}
        >
          <option value="basic">Basic 鈥?single-pass summarization</option>
          <option value="map_reduce">Map-Reduce 鈥?multi-chunk then combine</option>
        </select>
        <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>
          Strategy used when running Summarize tasks. Map-Reduce is better for long documents.
        </span>
      </label>
    </div>
  );
}

function DisplayTab() {
  const {
    showWorkflowDetails,
    showTechnicalCitationMetadata,
    density,
    sourceDrawerDefaultOpen,
    defaultTaskType,
    setShowWorkflowDetails,
    setShowTechnicalCitationMetadata,
    setDensity,
    setSourceDrawerDefaultOpen,
    setDefaultTaskType,
  } = useWorkspacePreferences();

  const toggleRow = (label: string, value: boolean, onChange: (v: boolean) => void) => (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: density === 'compact' ? '10px 0' : '12px 0',
      borderBottom: '1px solid var(--color-border-subtle)',
    }}>
      <span style={{ fontSize: '14px', color: 'var(--color-text-primary)', fontWeight: 500 }}>{label}</span>
      <button
        type="button"
        onClick={() => onChange(!value)}
        style={{
          width: '42px',
          height: '24px',
          borderRadius: '12px',
          border: 'none',
          background: value ? 'var(--color-brand-500)' : 'var(--color-border-default)',
          cursor: 'pointer',
          position: 'relative',
          transition: 'background var(--transition-fast)',
          flexShrink: 0,
        }}
      >
        <span style={{
          position: 'absolute',
          top: '3px',
          left: value ? '21px' : '3px',
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          background: '#fff',
          transition: 'left var(--transition-fast)',
          boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
        }} />
      </button>
    </div>
  );

  return (
    <div style={{ display: 'grid', gap: density === 'compact' ? '12px' : '16px' }}>
      <div style={{
        padding: '12px 14px',
        background: 'var(--color-canvas-subtle)',
        border: '1px solid var(--color-border-subtle)',
        borderRadius: 'var(--radius-md)',
        fontSize: '13px',
        color: 'var(--color-text-tertiary)',
      }}>
        Preferences are stored locally in your browser. They do not affect the backend.
      </div>

      {toggleRow('Show workflow details', showWorkflowDetails, setShowWorkflowDetails)}
      {toggleRow('Show technical citation metadata', showTechnicalCitationMetadata, setShowTechnicalCitationMetadata)}
      {toggleRow('Source drawer opens by default', sourceDrawerDefaultOpen, setSourceDrawerDefaultOpen)}

      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: density === 'compact' ? '10px 0' : '12px 0',
        borderBottom: '1px solid var(--color-border-subtle)',
      }}>
        <span style={{ fontSize: '14px', color: 'var(--color-text-primary)', fontWeight: 500 }}>Density</span>
        <div style={{ display: 'flex', gap: '4px' }}>
          {(['comfortable', 'compact'] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDensity(d)}
              style={{
                padding: '5px 12px',
                borderRadius: 'var(--radius-md)',
                border: density === d ? '1px solid var(--color-brand-200)' : '1px solid var(--color-border-subtle)',
                background: density === d ? 'var(--color-brand-50)' : 'transparent',
                color: density === d ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: density === d ? 700 : 500,
                textTransform: 'capitalize',
                transition: 'all var(--transition-fast)',
              }}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: density === 'compact' ? '10px 0' : '12px 0',
        borderBottom: '1px solid var(--color-border-subtle)',
      }}>
        <span style={{ fontSize: '14px', color: 'var(--color-text-primary)', fontWeight: 500 }}>Default operation</span>
        <div style={{ display: 'flex', gap: '4px' }}>
          {(['auto', 'chat', 'summarize', 'compare'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setDefaultTaskType(t)}
              style={{
                padding: '5px 12px',
                borderRadius: 'var(--radius-md)',
                border: defaultTaskType === t ? '1px solid var(--color-brand-200)' : '1px solid var(--color-border-subtle)',
                background: defaultTaskType === t ? 'var(--color-brand-50)' : 'transparent',
                color: defaultTaskType === t ? 'var(--color-brand-600)' : 'var(--color-text-tertiary)',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: defaultTaskType === t ? 700 : 500,
                textTransform: 'capitalize',
                transition: 'all var(--transition-fast)',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SourcesTab() {
  const { density } = useWorkspacePreferences();
  const [skills, setSkills] = useState<SourceSkillItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manifestText, setManifestText] = useState('{\n  "id": "local.project_csv",\n  "name": "Project CSV Skill",\n  "kind": "source",\n  "version": "0.1.0",\n  "description": "Convert project CSV rows into searchable text.",\n  "handler": "csv.extract",\n  "input_kinds": [".csv"],\n  "output_type": "SourceLoadResult",\n  "source_media": "text",\n  "source_kind": "csv_file",\n  "loader_name": "csv.extract",\n  "permissions": ["read_file", "write_index"],\n  "safety_notes": ["uses_builtin_handler"]\n}');
  const [manifestResult, setManifestResult] = useState<SourceSkillValidationResponse | null>(null);
  const [manifestBusy, setManifestBusy] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const loadSkills = () => {
    setLoading(true);
    setError(null);
    SkillService.listSourceSkills()
      .then((items) => setSkills(items))
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Unable to load source skills.');
        setSkills([]);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSkills();
  }, []);

  const handleToggleSkill = async (skill: SourceSkillItem, enable: boolean) => {
    setTogglingId(skill.id);
    setError(null);
    try {
      if (enable) {
        await SkillService.enableLocalSourceSkill(skill.id);
      } else {
        await SkillService.disableLocalSourceSkill(skill.id);
      }
      loadSkills();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to ${enable ? 'enable' : 'disable'} skill.`;
      setError(msg);
    } finally {
      setTogglingId(null);
    }
  };

  const parseManifest = (): Record<string, unknown> | null => {
    try {
      return JSON.parse(manifestText) as Record<string, unknown>;
    } catch (err) {
      setManifestResult({
        ok: false,
        skill_id: null,
        errors: [err instanceof Error ? err.message : 'Invalid JSON manifest.'],
        warnings: [],
        executable: false,
        reason: 'Manifest JSON parse failed.',
        skill: null,
      });
      return null;
    }
  };

  const validateManifest = () => {
    const manifest = parseManifest();
    if (!manifest) return;
    setManifestBusy(true);
    SkillService.validateSourceSkillManifest(manifest)
      .then(setManifestResult)
      .catch((err) => setManifestResult({
        ok: false,
        skill_id: null,
        errors: [err instanceof Error ? err.message : 'Validation failed.'],
        warnings: [],
        executable: false,
        reason: 'Request failed.',
        skill: null,
      }))
      .finally(() => setManifestBusy(false));
  };

  const registerManifest = () => {
    const manifest = parseManifest();
    if (!manifest) return;
    setManifestBusy(true);
    SkillService.registerSourceSkillManifest(manifest)
      .then((result) => {
        setManifestResult(result);
        if (result.ok) loadSkills();
      })
      .catch((err) => setManifestResult({
        ok: false,
        skill_id: null,
        errors: [err instanceof Error ? err.message : 'Registration failed.'],
        warnings: [],
        executable: false,
        reason: 'Request failed.',
        skill: null,
      }))
      .finally(() => setManifestBusy(false));
  };

  const groups = [
    { label: 'Implemented', items: skills.filter((skill) => skill.status === 'implemented') },
    { label: 'Local', items: skills.filter((skill) => skill.origin === 'local' && skill.status === 'local') },
    { label: 'Disabled', items: skills.filter((skill) => skill.status === 'disabled') },
    { label: 'Future', items: skills.filter((skill) => skill.status === 'future') },
    { label: 'Invalid', items: skills.filter((skill) => skill.status === 'invalid') },
  ].filter((group) => group.items.length > 0);

  return (
    <div style={{ display: 'grid', gap: density === 'compact' ? '10px' : '14px' }}>
      <div style={{
        padding: '12px 14px',
        background: 'var(--color-canvas-subtle)',
        border: '1px solid var(--color-border-subtle)',
        borderRadius: 'var(--radius-md)',
        fontSize: '13px',
        color: 'var(--color-text-tertiary)',
      }}>
        Source skills define what kinds of documents MindDock can ingest and retrieve. Local manifests bind only to trusted built-in handlers.
      </div>

      {loading && <p style={{ color: 'var(--color-text-tertiary)', fontSize: '14px' }}>Loading source skills...</p>}
      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-error-bg)', border: '1px solid var(--color-error-border)', borderRadius: 'var(--radius-md)', color: 'var(--color-error-text)', fontSize: '13px' }}>
          {error}
        </div>
      )}

      {!loading && !error && groups.map((group) => (
        <div key={group.label} style={{ display: 'grid', gap: density === 'compact' ? '8px' : '10px' }}>
          <div style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {group.label}
          </div>
          {group.items.map((skill) => (
            <SourceSkillCard
              key={skill.id}
              skill={skill}
              density={density}
              togglingId={togglingId}
              onToggle={handleToggleSkill}
            />
          ))}
        </div>
      ))}

      <div style={{ display: 'grid', gap: '10px', paddingTop: '6px', borderTop: '1px solid var(--color-border-subtle)' }}>
        <div style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Register Local Manifest
        </div>
        <textarea
          data-testid="source-skill-manifest"
          value={manifestText}
          onChange={(event) => setManifestText(event.target.value)}
          style={{ ...fieldStyle, minHeight: '150px', fontFamily: 'var(--font-mono)', fontSize: '12px', resize: 'vertical' }}
        />
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            type="button"
            onClick={validateManifest}
            disabled={manifestBusy}
            style={{ padding: '8px 13px', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-subtle)', background: 'var(--color-canvas-subtle)', color: 'var(--color-text-secondary)', cursor: manifestBusy ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: '13px' }}
          >
            Validate
          </button>
          <button
            type="button"
            onClick={registerManifest}
            disabled={manifestBusy}
            style={{ padding: '8px 13px', borderRadius: 'var(--radius-md)', border: 'none', background: 'var(--color-brand-600)', color: '#fff', cursor: manifestBusy ? 'not-allowed' : 'pointer', fontWeight: 700, fontSize: '13px' }}
          >
            Register
          </button>
        </div>
        {manifestResult && (
          <div
            data-testid="source-skill-manifest-result"
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-md)',
              background: manifestResult.ok ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
              border: `1px solid ${manifestResult.ok ? 'var(--color-success-border)' : 'var(--color-error-border)'}`,
              color: manifestResult.ok ? 'var(--color-success-text)' : 'var(--color-error-text)',
              fontSize: '13px',
            }}
          >
            <strong>{manifestResult.ok ? 'Valid manifest' : 'Manifest rejected'}</strong>
            <div style={{ marginTop: '4px' }}>{manifestResult.reason}</div>
            {[...manifestResult.errors, ...manifestResult.warnings].map((item) => (
              <div key={item} style={{ marginTop: '3px' }}>{item}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SourceSkillCard({
  skill,
  density,
  togglingId,
  onToggle,
}: {
  skill: SourceSkillItem;
  density: 'comfortable' | 'compact';
  togglingId: string | null;
  onToggle: (skill: SourceSkillItem, enable: boolean) => void;
}) {
  const isEnabled = skill.enabled && skill.status !== 'future' && skill.status !== 'disabled';
  const input = skill.input_kinds.length ? skill.input_kinds.join(', ') : '-';
  const limitations = skill.limitations.length ? skill.limitations.join(', ') : '-';
  const capabilities = skill.capabilities.length ? skill.capabilities.join(', ') : '-';

  const canDisable = skill.origin === 'local' && skill.status === 'local';
  const canEnable = skill.origin === 'local' && skill.status === 'disabled';
  const isToggling = togglingId === skill.id;

  return (
    <div
      data-testid={`source-skill-${skill.id}`}
      style={{
        padding: density === 'compact' ? '12px 14px' : '14px 16px',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--color-border-subtle)',
        background: isEnabled ? 'var(--color-surface)' : 'var(--color-canvas-subtle)',
        opacity: isEnabled ? 1 : 0.72,
        boxShadow: isEnabled ? 'var(--shadow-sm)' : 'none',
        transition: 'all var(--transition-fast)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', marginBottom: '8px' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-text-primary)' }}>{skill.name}</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere' }}>{skill.id}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {(canEnable || canDisable) && (
            <button
              type="button"
              onClick={() => onToggle(skill, canEnable)}
              disabled={isToggling}
              data-testid={`source-skill-toggle-${skill.id}`}
              style={{
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                border: canEnable ? '1px solid var(--color-success-border)' : '1px solid var(--color-error-border)',
                background: canEnable ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                color: canEnable ? 'var(--color-success-text)' : 'var(--color-error-text)',
                fontSize: '11px',
                fontWeight: 700,
                cursor: isToggling ? 'not-allowed' : 'pointer',
                opacity: isToggling ? 0.6 : 1,
                transition: 'all var(--transition-fast)',
              }}
            >
              {isToggling ? '…' : canEnable ? 'Enable' : 'Disable'}
            </button>
          )}
          <span
            style={{
              fontSize: '10px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              padding: '3px 10px',
              borderRadius: 'var(--radius-full)',
              background: isEnabled ? 'var(--color-success-bg)' : 'var(--color-canvas)',
              color: isEnabled ? 'var(--color-success-text)' : 'var(--color-text-tertiary)',
              border: `1px solid ${isEnabled ? 'var(--color-success-border)' : 'var(--color-border-subtle)'}`,
            }}
          >
            {skill.status}
          </span>
        </div>
      </div>
      <div style={{ display: 'grid', gap: '3px', fontSize: '13px', color: 'var(--color-text-tertiary)', lineHeight: 1.5 }}>
        <div><span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Handler:</span> {skill.handler || '-'}</div>
        <div><span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Input:</span> {input}</div>
        <div><span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Capabilities:</span> {capabilities}</div>
        <div><span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Limit:</span> {limitations}</div>
      </div>
    </div>
  );
}
