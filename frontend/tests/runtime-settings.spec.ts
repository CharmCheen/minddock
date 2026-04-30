import { expect, Page, test } from '@playwright/test';

interface RuntimeConfigMock {
  apiKeyMasked: boolean;
  configSource: string;
  enabled?: boolean;
  model?: string;
  afterSave?: RuntimeConfigMock;
}

async function mockRuntimeConfig(page: Page, mock: RuntimeConfigMock) {
  let current = mock;

  const configBody = (config: RuntimeConfigMock) => {
    const enabled = config.enabled ?? true;
    return {
      provider: 'openai_compatible',
      base_url: 'https://api.example.com/v1',
      model: config.model || 'old-model',
      api_key_masked: config.apiKeyMasked,
      enabled,
      config_source: config.configSource,
    };
  };

  await page.route('**/health', (route) => {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });

  await page.route('**/frontend/runtime-config', async (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(configBody(current)),
      });
    }

    if (route.request().method() === 'PUT') {
      current = current.afterSave || current;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(configBody(current)),
      });
    }

    return route.fallback();
  });
}

test.describe('runtime settings API key save semantics', () => {
  test('leaves api_key out of save payload when a stored key exists and the field is blank', async ({ page }) => {
    await mockRuntimeConfig(page, { apiKeyMasked: true, configSource: 'active_config_env' });
    let savedPayload: Record<string, unknown> | null = null;

    await page.route('**/frontend/runtime-config', async (route) => {
      if (route.request().method() !== 'PUT') return route.fallback();
      savedPayload = route.request().postDataJSON();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          provider: 'openai_compatible',
          base_url: 'https://api.example.com/v1',
          model: 'new-model',
          api_key_masked: true,
          enabled: true,
          config_source: 'active_config_env',
        }),
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();

    const apiKey = page.getByTestId('runtime-api-key');
    await expect(apiKey).toHaveAttribute('placeholder', 'Configured - leave blank to keep current key');
    await expect(apiKey).toHaveValue('');

    await page.getByTestId('runtime-model').fill('new-model');
    await page.getByTestId('runtime-save').click();

    await expect.poll(() => savedPayload).not.toBeNull();
    expect(savedPayload).toMatchObject({
      provider: 'openai_compatible',
      base_url: 'https://api.example.com/v1',
      model: 'new-model',
      enabled: true,
    });
    expect(savedPayload).not.toHaveProperty('api_key');
  });

  test('shows missing-key copy when no key exists', async ({ page }) => {
    await mockRuntimeConfig(page, { apiKeyMasked: false, configSource: 'active_config_disabled' });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();

    await expect(page.getByTestId('runtime-api-key')).toHaveAttribute('placeholder', 'Enter API key');
    await expect(page.getByText('API key is kept only for the current backend session. After restarting the backend, re-enter it or set LLM_API_KEY in your environment.')).toBeVisible();
    await expect(page.getByText('Runtime is missing an API key.')).toBeVisible();
  });

  test('empty api key test connection validates locally without backend call', async ({ page }) => {
    await mockRuntimeConfig(page, { apiKeyMasked: false, configSource: 'active_config_disabled' });
    let testConnectionCalled = false;

    await page.route('**/frontend/runtime-config/test', (route) => {
      testConnectionCalled = true;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          message: 'Unexpected backend call',
          error_kind: 'network_error',
        }),
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();
    await page.getByRole('button', { name: 'Test Connection' }).click();

    await expect(page.getByText('API key is required to test this runtime. Enter a key or set LLM_API_KEY in the backend environment.')).toBeVisible();
    expect(testConnectionCalled).toBe(false);
  });

  test('save with enabled runtime but no active key shows honest warning', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: false,
      configSource: 'active_config_disabled',
      enabled: true,
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();
    await page.getByTestId('runtime-model').fill('new-model');
    await page.getByTestId('runtime-save').click();

    await expect(page.getByText('Saved, but the API key is not active in this backend session. Re-enter the key or set LLM_API_KEY, then save again.')).toBeVisible();
    await expect(page.getByText('Saved. Runtime changes are active for new runs.')).toHaveCount(0);
  });

  test('save message is clear when custom runtime is disabled', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: false,
      configSource: 'active_config_disabled',
      enabled: false,
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();
    await page.getByTestId('runtime-model').fill('new-model');
    await page.getByTestId('runtime-save').click();

    await expect(page.getByText('Saved. Custom runtime is disabled; MindDock will use the default runtime.')).toBeVisible();
  });

  test('save message is active when backend reports an active key', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: true,
      configSource: 'active_config_env',
      enabled: true,
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();
    await page.getByTestId('runtime-model').fill('new-model');
    await page.getByTestId('runtime-save').click();

    await expect(page.getByText('Saved. Runtime changes are active for new runs.')).toBeVisible();
  });

  test('fresh api key save reports active after backend accepts the session key', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: false,
      configSource: 'active_config_disabled',
      enabled: true,
      afterSave: {
        apiKeyMasked: true,
        configSource: 'active_config_env',
        enabled: true,
        model: 'new-model',
      },
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open settings' }).click();
    await page.getByTestId('runtime-api-key').fill('sk-new-session-key');
    await page.getByTestId('runtime-model').fill('new-model');
    await page.getByTestId('runtime-save').click();

    await expect(page.getByText('Saved. Runtime changes are active for new runs.')).toBeVisible();
    await expect(page.getByText('Saved, but the API key is not active in this backend session. Re-enter the key or set LLM_API_KEY, then save again.')).toHaveCount(0);
  });
});

test.describe('runtime status truth display', () => {
  test('does not show Configured when key marker exists but no active process key exists', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: true,
      configSource: 'active_config_disabled',
      enabled: true,
    });

    await page.goto('/');
    await expect(page.getByTestId('runtime-status')).toContainText('Missing API key');
    await expect(page.getByTestId('runtime-status')).not.toContainText('Configured');

    await page.getByRole('button', { name: 'Open settings' }).click();
    await expect(page.getByTestId('runtime-current-status')).toContainText('Missing API key');
    await expect(page.getByTestId('runtime-api-key')).toHaveAttribute('placeholder', 'Enter API key');
    await expect(page.getByText('Runtime is missing an API key.')).toBeVisible();
  });

  test('shows Configured consistently when config_source is active', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: true,
      configSource: 'active_config_env',
      enabled: true,
    });

    await page.goto('/');
    await expect(page.getByTestId('runtime-status')).toContainText('Configured');

    await page.getByRole('button', { name: 'Open settings' }).click();
    await expect(page.getByTestId('runtime-current-status')).toContainText('Configured');
    await expect(page.getByTestId('runtime-api-key')).toHaveAttribute('placeholder', 'Configured - leave blank to keep current key');
  });

  test('shows Disabled consistently when runtime config is disabled', async ({ page }) => {
    await mockRuntimeConfig(page, {
      apiKeyMasked: false,
      configSource: 'active_config_disabled',
      enabled: false,
    });

    await page.goto('/');
    await expect(page.getByTestId('runtime-status')).toContainText('Disabled');

    await page.getByRole('button', { name: 'Open settings' }).click();
    await expect(page.getByTestId('runtime-current-status')).toContainText('Disabled');
    await expect(page.getByText('Runtime is missing an API key.')).toHaveCount(0);
  });
});
