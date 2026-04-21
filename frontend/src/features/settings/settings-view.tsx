import React, { useEffect, useState } from 'react';
import { RuntimeFormValues, useSettingsStore } from './store';

const PROVIDER_LABELS: Record<string, string> = {
  openai_compatible: 'OpenAI-Compatible',
};

function runtimeState(config: ReturnType<typeof useSettingsStore.getState>['config']) {
  if (!config) return { label: 'Missing', color: '#f59e0b' };
  if (config.enabled && config.api_key_masked) return { label: 'Configured', color: '#22c55e' };
  if (config.enabled && !config.api_key_masked) return { label: 'Missing API Key', color: '#f59e0b' };
  return { label: 'Disabled', color: '#94a3b8' };
}

const fieldStyle: React.CSSProperties = {
  width: '100%',
  padding: '9px 11px',
  background: '#0f172a',
  border: '1px solid #334155',
  borderRadius: '6px',
  color: '#e2e8f0',
  fontSize: '14px',
  boxSizing: 'border-box',
};

export const SettingsView: React.FC<{ onClose: () => void }> = ({ onClose }) => {
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

  const status = runtimeState(config);
  const providerLabel = PROVIDER_LABELS[config?.provider || form.provider] || 'OpenAI-Compatible';
  const hasStoredKey = Boolean(config?.api_key_masked);
  const canSave = isDirty && !saving;
  const canTest = Boolean(form.base_url.trim() && form.model.trim() && form.api_key.trim()) && !testing;

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
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.56)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}
    >
      <div
        style={{
          width: '720px',
          maxWidth: '96vw',
          maxHeight: '92vh',
          overflow: 'hidden',
          background: '#111827',
          border: '1px solid #334155',
          borderRadius: '10px',
          boxShadow: '0 24px 70px rgba(0, 0, 0, 0.45)',
          color: '#e2e8f0',
          display: 'grid',
          gridTemplateColumns: '190px 1fr',
        }}
      >
        <aside style={{ borderRight: '1px solid #334155', background: '#0f172a', padding: '18px' }}>
          <h2 id="settings-title" style={{ margin: '0 0 18px', fontSize: '16px', fontWeight: 700 }}>
            Settings
          </h2>
          <button
            type="button"
            data-testid="settings-runtime-tab"
            style={{
              width: '100%',
              padding: '9px 10px',
              borderRadius: '6px',
              border: '1px solid #3b82f6',
              background: '#1d4ed833',
              color: '#bfdbfe',
              fontSize: '13px',
              fontWeight: 700,
              textAlign: 'left',
            }}
          >
            Models & Runtime
          </button>
        </aside>

        <section style={{ padding: '22px', overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start' }}>
            <div>
              <h3 style={{ margin: '0 0 5px', fontSize: '18px' }}>Models & Runtime</h3>
              <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>
                Configure the OpenAI-compatible endpoint used by new agent runs.
              </p>
            </div>
            <button
              type="button"
              aria-label="Close settings"
              onClick={onClose}
              style={{
                width: '30px',
                height: '30px',
                borderRadius: '6px',
                border: '1px solid #334155',
                background: '#0f172a',
                color: '#cbd5e1',
                cursor: 'pointer',
              }}
            >
              x
            </button>
          </div>

          <div
            data-testid="runtime-current-status"
            style={{
              marginTop: '18px',
              padding: '13px 14px',
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: '8px',
              display: 'grid',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase' }}>
                Current Runtime
              </span>
              <span
                style={{
                  padding: '3px 8px',
                  borderRadius: '999px',
                  background: `${status.color}22`,
                  border: `1px solid ${status.color}66`,
                  color: status.color,
                  fontSize: '11px',
                  fontWeight: 700,
                }}
              >
                {successMessage ? 'Saved' : error ? 'Error' : status.label}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '5px 10px', fontSize: '13px' }}>
              <span style={{ color: '#64748b' }}>Provider Type</span>
              <span>{providerLabel}</span>
              <span style={{ color: '#64748b' }}>Base URL</span>
              <span style={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}>{config?.base_url || 'Not configured'}</span>
              <span style={{ color: '#64748b' }}>Model</span>
              <span>{config?.model || 'Not configured'}</span>
              <span style={{ color: '#64748b' }}>API Key</span>
              <span>{hasStoredKey ? '********' : 'Not configured'}</span>
            </div>
          </div>

          {!loading && !config?.api_key_masked && (
            <div
              style={{
                marginTop: '12px',
                padding: '10px 12px',
                borderRadius: '6px',
                background: '#713f1226',
                border: '1px solid #f59e0b55',
                color: '#fcd34d',
                fontSize: '13px',
              }}
            >
              Runtime is missing an API key. Add one here before running model-backed tasks.
            </div>
          )}

          {loading ? (
            <p style={{ color: '#94a3b8', fontSize: '14px' }}>Loading runtime settings...</p>
          ) : (
            <form
              data-testid="runtime-settings-form"
              onSubmit={(event) => {
                event.preventDefault();
                handleSave();
              }}
              style={{ marginTop: '18px', display: 'grid', gap: '14px' }}
            >
              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: '#94a3b8' }}>
                Provider Type
                <select
                  value={form.provider}
                  disabled
                  onChange={(event) => patchForm({ provider: event.target.value })}
                  style={{ ...fieldStyle, color: '#94a3b8' }}
                >
                  <option value="openai_compatible">OpenAI-Compatible</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: '#94a3b8' }}>
                Base URL
                <input
                  data-testid="runtime-base-url"
                  value={form.base_url}
                  onChange={(event) => patchForm({ base_url: event.target.value })}
                  placeholder="https://api.openai.com/v1"
                  style={fieldStyle}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: '#94a3b8' }}>
                API Key
                <input
                  data-testid="runtime-api-key"
                  type="password"
                  value={form.api_key}
                  onChange={(event) => patchForm({ api_key: event.target.value })}
                  placeholder={hasStoredKey ? 'Configured - leave blank to keep current key' : 'Enter API key'}
                  autoComplete="off"
                  style={fieldStyle}
                />
              </label>

              <label style={{ display: 'grid', gap: '5px', fontSize: '12px', color: '#94a3b8' }}>
                Model
                <input
                  data-testid="runtime-model"
                  value={form.model}
                  onChange={(event) => patchForm({ model: event.target.value })}
                  placeholder="gpt-4o-mini"
                  style={fieldStyle}
                />
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#cbd5e1', fontSize: '14px' }}>
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
                    padding: '10px 12px',
                    borderRadius: '6px',
                    background: testResult.success ? '#14532d33' : '#7f1d1d33',
                    border: `1px solid ${testResult.success ? '#22c55e55' : '#ef444455'}`,
                    color: testResult.success ? '#86efac' : '#fca5a5',
                    fontSize: '13px',
                  }}
                >
                  <strong>{testResult.success ? 'Connection OK' : 'Connection failed'}</strong>
                  <div style={{ marginTop: '3px' }}>{testResult.message}</div>
                </div>
              )}

              {error && (
                <div style={{ padding: '10px 12px', background: '#7f1d1d33', border: '1px solid #ef444455', borderRadius: '6px', color: '#fca5a5', fontSize: '13px' }}>
                  {error}
                </div>
              )}
              {successMessage && (
                <div style={{ padding: '10px 12px', background: '#14532d33', border: '1px solid #22c55e55', borderRadius: '6px', color: '#86efac', fontSize: '13px' }}>
                  {successMessage}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginTop: '4px' }}>
                <button
                  type="button"
                  onClick={() => void resetConfig()}
                  disabled={resetting}
                  style={{
                    padding: '9px 12px',
                    borderRadius: '6px',
                    border: '1px solid #7f1d1d',
                    background: '#0f172a',
                    color: '#fca5a5',
                    cursor: resetting ? 'not-allowed' : 'pointer',
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
                      padding: '9px 12px',
                      borderRadius: '6px',
                      border: '1px solid #334155',
                      background: '#0f172a',
                      color: '#e2e8f0',
                      cursor: canTest ? 'pointer' : 'not-allowed',
                      opacity: canTest ? 1 : 0.55,
                    }}
                  >
                    {testing ? 'Testing...' : 'Test Connection'}
                  </button>
                  <button
                    type="submit"
                    data-testid="runtime-save"
                    disabled={!canSave}
                    style={{
                      padding: '9px 16px',
                      borderRadius: '6px',
                      border: 'none',
                      background: '#2563eb',
                      color: '#fff',
                      fontWeight: 700,
                      cursor: canSave ? 'pointer' : 'not-allowed',
                      opacity: canSave ? 1 : 0.55,
                    }}
                  >
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
};
