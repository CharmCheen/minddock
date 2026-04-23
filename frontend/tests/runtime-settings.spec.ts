import { expect, Page, test } from '@playwright/test';

interface RuntimeConfigMock {
  apiKeyMasked: boolean;
  configSource: string;
  enabled?: boolean;
}

async function mockRuntimeConfig(page: Page, mock: RuntimeConfigMock) {
  const enabled = mock.enabled ?? true;

  await page.route('**/health', (route) => {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });

  await page.route('**/frontend/runtime-config', async (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          provider: 'openai_compatible',
          base_url: 'https://api.example.com/v1',
          model: 'old-model',
          api_key_masked: mock.apiKeyMasked,
          enabled,
          config_source: mock.configSource,
        }),
      });
    }

    if (route.request().method() === 'PUT') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          provider: 'openai_compatible',
          base_url: 'https://api.example.com/v1',
          model: 'new-model',
          api_key_masked: mock.apiKeyMasked,
          enabled,
          config_source: mock.configSource,
        }),
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
    await expect(page.getByText('Runtime is missing an API key.')).toBeVisible();
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
