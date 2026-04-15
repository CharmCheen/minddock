import React, { useEffect, useState } from 'react';
import { useSettingsStore } from './store';

export const SettingsView: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { config, loading, saving, error, successMessage, loadConfig, saveConfig } = useSettingsStore();

  const [provider, setProvider] = useState('openai_compatible');
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('gpt-4o-mini');
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (config) {
      setProvider(config.provider);
      setBaseUrl(config.base_url);
      setModel(config.model);
      setEnabled(config.enabled);
      // Only pre-fill apiKey if masked (i.e., already set) — never echo back plaintext
      setApiKey(config.api_key_masked ? '••••••••' : '');
    }
  }, [config]);

  const handleSave = async () => {
    await saveConfig({ provider, base_url: baseUrl, api_key: apiKey, model, enabled });
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#1e293b', borderRadius: '12px', padding: '28px',
        width: '480px', maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        color: '#e2e8f0',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>Runtime Settings</h2>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '20px', cursor: 'pointer', padding: '4px' }}
          >
            ×
          </button>
        </div>

        {loading && <p style={{ color: '#94a3b8', fontSize: '14px' }}>Loading...</p>}

        {!loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Provider */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', color: '#94a3b8', marginBottom: '6px' }}>Provider</label>
              <select
                value={provider}
                onChange={e => setProvider(e.target.value)}
                disabled
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px',
                }}
              >
                <option value="openai_compatible">OpenAI-Compatible</option>
              </select>
              <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#64748b' }}>Phase 1 supports OpenAI-compatible endpoints only</p>
            </div>

            {/* Base URL */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', color: '#94a3b8', marginBottom: '6px' }}>Base URL</label>
              <input
                type="text"
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1"
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', boxSizing: 'border-box',
                }}
              />
            </div>

            {/* API Key */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', color: '#94a3b8', marginBottom: '6px' }}>
                API Key {config?.api_key_masked && <span style={{ color: '#22c55e', fontSize: '11px' }}>(currently configured)</span>}
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={config?.api_key_masked ? 'Leave blank to keep current key' : 'sk-...'}
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Model */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', color: '#94a3b8', marginBottom: '6px' }}>Model</label>
              <input
                type="text"
                value={model}
                onChange={e => setModel(e.target.value)}
                placeholder="gpt-4o-mini"
                style={{
                  width: '100%', padding: '8px 12px', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Enabled toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <input
                type="checkbox"
                id="runtime-enabled"
                checked={enabled}
                onChange={e => setEnabled(e.target.checked)}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="runtime-enabled" style={{ fontSize: '14px', cursor: 'pointer' }}>
                Use this configuration for requests
              </label>
            </div>

            {/* Messages */}
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

            {/* Actions */}
            <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
              <button
                onClick={handleSave}
                disabled={saving}
                style={{
                  flex: 1, padding: '9px 16px', background: '#3b82f6', border: 'none',
                  borderRadius: '6px', color: '#fff', fontSize: '14px', fontWeight: '500',
                  cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1,
                }}
              >
                {saving ? 'Saving...' : 'Save Configuration'}
              </button>
              <button
                onClick={onClose}
                style={{
                  padding: '9px 16px', background: '#334155', border: 'none',
                  borderRadius: '6px', color: '#e2e8f0', fontSize: '14px', cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
