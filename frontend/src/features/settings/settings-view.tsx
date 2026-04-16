import React, { useEffect } from 'react';
import { useSettingsStore, RuntimeFormValues } from './store';

export const SettingsView: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const {
    config,
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

  // Local form state — single source of truth for user edits
  const [provider, setProvider] = React.useState('openai_compatible');
  const [baseUrl, setBaseUrl] = React.useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = React.useState('');
  const [model, setModel] = React.useState('gpt-4o-mini');
  const [enabled, setEnabled] = React.useState(false);

  // Load config on mount
  useEffect(() => { loadConfig(); }, [loadConfig]);

  // Sync local state when config is reloaded (after save/reset/load) — NOT on every render
  useEffect(() => {
    if (!config) return;
    setProvider(config.provider);
    setBaseUrl(config.base_url);
    setModel(config.model);
    setEnabled(config.enabled);
    setApiKey(config.api_key_masked ? '••••••••' : '');
  }, [config]);

  // Helper: build current form snapshot from local state
  const currentForm = (): RuntimeFormValues => ({
    provider,
    base_url: baseUrl,
    api_key: apiKey,
    model,
    enabled,
  });

  // Sync dirty flag whenever local state changes
  const handleChange = (updater: () => void) => {
    updater();
    // Read fresh store state after React flushes the setState
    setTimeout(() => {
      updateFormValues(currentForm());
    }, 0);
  };

  const handleSave = async () => {
    // If api_key shows placeholder, treat as empty (keep existing key on server)
    const effectiveKey = apiKey === '••••••••' ? '' : apiKey;
    await saveConfig({ ...currentForm(), api_key: effectiveKey });
  };

  const handleTest = async () => {
    const effectiveKey = apiKey === '••••••••' ? '' : apiKey;
    await testConnection({ provider, base_url: baseUrl, api_key: effectiveKey, model });
  };

  const handleReset = async () => {
    await resetConfig();
  };

  // Derived display values for active status banner
  const isCustomActive = !!(config?.enabled);
  const activeStatusColor = isCustomActive ? '#22c55e' : '#64748b';
  const activeStatusLabel = isCustomActive ? 'Custom Active' : 'Default Runtime';
  const activeBaseUrl = config?.base_url ?? 'https://api.openai.com/v1';
  const activeModel = config?.model ?? 'gpt-4o-mini';
  const activeHasKey = config?.api_key_masked ?? false;

  const testResultIcon = testResult ? (testResult.success ? '✓' : '✗') : null;
  const testResultBg = testResult ? (testResult.success ? '#14532d' : '#7f1d1d') : 'transparent';
  const testResultColor = testResult ? (testResult.success ? '#86efac' : '#fca5a5') : '#e2e8f0';
  const testResultLabel = testResult
    ? testResult.success
      ? 'Connection OK'
      : `Failed${testResult.errorKind ? ` — ${testResult.errorKind.replace('_', ' ')}` : ''}`
    : null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#1e293b', borderRadius: '12px', padding: '28px',
        width: '500px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        color: '#e2e8f0',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>Runtime Settings</h2>
            {isDirty && (
              <span style={{
                padding: '2px 8px', background: '#713f12', borderRadius: '4px',
                fontSize: '11px', color: '#fde68a', fontWeight: '500',
              }}>
                Unsaved changes
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '20px', cursor: 'pointer', padding: '4px' }}
          >
            ×
          </button>
        </div>

        {loading && <p style={{ color: '#94a3b8', fontSize: '14px' }}>Loading...</p>}

        {!loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

            {/* ── A: Active Status Banner ── */}
            <div style={{
              padding: '10px 14px',
              background: '#0f172a',
              borderRadius: '8px',
              border: `1px solid ${isCustomActive ? '#22c55e33' : '#334155'}`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '11px', color: '#64748b', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Currently Active
                </span>
                <span style={{
                  padding: '2px 8px',
                  background: `${activeStatusColor}22`,
                  border: `1px solid ${activeStatusColor}66`,
                  borderRadius: '4px',
                  fontSize: '11px',
                  color: activeStatusColor,
                  fontWeight: '700',
                }}>
                  {activeStatusLabel}
                </span>
              </div>
              <div style={{ fontSize: '13px', color: '#cbd5e1', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Provider: </span>
                  <span>{config?.provider ?? '—'}</span>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Endpoint: </span>
                  <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{activeBaseUrl}</span>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Model: </span>
                  <span>{activeModel}</span>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>API Key: </span>
                  <span>{activeHasKey ? '•••••••• (stored)' : 'Not configured'}</span>
                </div>
              </div>
            </div>

            <div style={{ borderTop: '1px solid #334155' }} />

            {/* Provider (fixed) */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>Provider</label>
              <select
                value={provider}
                disabled
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: '6px', color: '#94a3b8', fontSize: '14px',
                }}
              >
                <option value="openai_compatible">OpenAI-Compatible</option>
              </select>
              <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#475569' }}>Phase 1: only OpenAI-compatible endpoints</p>
            </div>

            {/* Base URL */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>Base URL</label>
              <input
                type="text"
                value={baseUrl}
                onChange={e => handleChange(() => setBaseUrl(e.target.value))}
                placeholder="https://api.openai.com/v1"
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a',
                  border: `1px solid ${isDirty ? '#f59e0b' : '#334155'}`,
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', boxSizing: 'border-box',
                }}
              />
            </div>

            {/* API Key */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>
                API Key{activeHasKey && <span style={{ color: '#22c55e', fontSize: '11px' }}> — stored</span>}
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={e => handleChange(() => setApiKey(e.target.value))}
                placeholder={activeHasKey ? 'Leave blank to keep current' : 'sk-...'}
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a',
                  border: `1px solid ${isDirty ? '#f59e0b' : '#334155'}`,
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Model */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>Model</label>
              <input
                type="text"
                value={model}
                onChange={e => handleChange(() => setModel(e.target.value))}
                placeholder="gpt-4o-mini"
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a',
                  border: `1px solid ${isDirty ? '#f59e0b' : '#334155'}`,
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Enabled */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <input
                type="checkbox"
                id="runtime-enabled"
                checked={enabled}
                onChange={e => handleChange(() => setEnabled(e.target.checked))}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="runtime-enabled" style={{ fontSize: '14px', cursor: 'pointer' }}>
                Enable this runtime
              </label>
            </div>

            {/* ── C: Test Result Banner ── */}
            {testResult && (
              <div style={{
                padding: '8px 12px', borderRadius: '6px',
                background: testResultBg,
                border: `1px solid ${testResult.success ? '#22c55e44' : '#ef444444'}`,
                fontSize: '13px', color: testResultColor,
                display: 'flex', alignItems: 'flex-start', gap: '8px',
              }}>
                <span style={{ fontWeight: '700', fontSize: '16px', lineHeight: '1.2' }}>{testResultIcon}</span>
                <div>
                  <div style={{ fontWeight: '600' }}>{testResultLabel}</div>
                  <div style={{ fontSize: '12px', opacity: 0.85, marginTop: '2px' }}>{testResult.message}</div>
                </div>
              </div>
            )}

            {/* ── D: Success / Error ── */}
            {error && (
              <div style={{ padding: '8px 12px', background: '#7f1d1d', borderRadius: '6px', fontSize: '13px', color: '#fca5a5' }}>
                {error}
              </div>
            )}
            {successMessage && (
              <div style={{ padding: '8px 12px', background: '#14532d', borderRadius: '6px', fontSize: '13px', color: '#86efac' }}>
                {successMessage}
              </div>
            )}

            {/* ── Actions ── */}
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
              <button
                onClick={handleSave}
                disabled={saving || !isDirty}
                title={!isDirty ? 'No changes to save' : 'Save and activate immediately'}
                style={{
                  flex: 2, padding: '9px 16px',
                  background: '#3b82f6', border: 'none', borderRadius: '6px',
                  color: '#fff', fontSize: '14px', fontWeight: '600',
                  cursor: (saving || !isDirty) ? 'not-allowed' : 'pointer',
                  opacity: (saving || !isDirty) ? 0.45 : 1,
                }}
              >
                {saving ? 'Saving...' : 'Save & Activate'}
              </button>
              <button
                onClick={handleTest}
                disabled={testing}
                title="Verify connection without saving"
                style={{
                  flex: 1.5, padding: '9px 12px',
                  background: '#0f172a', border: '1px solid #334155', borderRadius: '6px',
                  color: '#e2e8f0', fontSize: '14px',
                  cursor: testing ? 'not-allowed' : 'pointer',
                  opacity: testing ? 0.55 : 1,
                }}
              >
                {testing ? 'Testing...' : 'Test Connection'}
              </button>
              <button
                onClick={handleReset}
                disabled={resetting}
                title="Restore default runtime, discard custom config"
                style={{
                  padding: '9px 12px',
                  background: '#0f172a', border: '1px solid #991b1b', borderRadius: '6px',
                  color: '#fca5a5', fontSize: '14px',
                  cursor: resetting ? 'not-allowed' : 'pointer',
                  opacity: resetting ? 0.55 : 1,
                }}
              >
                {resetting ? '…' : 'Reset'}
              </button>
            </div>

            <button
              onClick={onClose}
              style={{
                width: '100%', padding: '8px',
                background: '#334155', border: 'none', borderRadius: '6px',
                color: '#e2e8f0', fontSize: '14px', cursor: 'pointer',
              }}
            >
              {isDirty ? 'Cancel (changes discarded)' : 'Close'}
            </button>

          </div>
        )}
      </div>
    </div>
  );
};
