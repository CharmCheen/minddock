import { expect, Page, test } from '@playwright/test';

/** Minimal skill mock with all fields the SourceSkillCard component accesses. */
function skillMock(overrides: Record<string, unknown>) {
  return {
    id: '',
    name: '',
    kind: 'source',
    version: '1.0.0',
    status: 'implemented',
    description: '',
    input_kinds: [] as string[],
    output_type: 'SourceLoadResult',
    source_media: 'text',
    source_kind: 'text_file',
    loader_name: null,
    handler: null,
    handler_name: null,
    capabilities: [] as string[],
    providers: [] as string[],
    limitations: [] as string[],
    permissions: [] as string[],
    safety_notes: [] as string[],
    config_schema: [] as unknown[],
    config_keys: [] as string[],
    bindable: false,
    executable: false,
    enabled: true,
    origin: 'builtin',
    trusted: true,
    built_in: true,
    category: 'text',
    supported_extensions: [] as string[],
    supported_mime_types: [] as string[],
    control_plane: 'trusted_builtin',
    extension_model: 'none',
    future_market_ready: false,
    market_boundary: 'none',
    installable: false,
    remote_install_supported: false,
    arbitrary_code_execution: false,
    ...overrides,
  };
}

const CSV_EXTRACT = skillMock({
  id: 'csv.extract',
  name: 'CSV Rows as Text',
  input_kinds: ['.csv'],
  source_kind: 'csv_file',
  loader_name: 'csv.extract',
  handler: 'csv.extract',
  handler_name: 'csv.extract',
  capabilities: ['csv_rows_as_text'],
  limitations: ['no_excel'],
  permissions: ['read_file', 'write_index'],
  supported_extensions: ['.csv'],
  category: 'data',
});

const LOCAL_PROJECT_CSV = skillMock({
  id: 'local.project_csv',
  name: 'Project CSV Skill',
  version: '0.1.0',
  status: 'local',
  input_kinds: ['.csv'],
  source_kind: 'csv_file',
  loader_name: 'csv.extract',
  handler: 'csv.extract',
  handler_name: 'csv.extract',
  capabilities: ['csv_rows_as_text'],
  permissions: ['read_file'],
  safety_notes: ['uses_builtin_handler'],
  origin: 'local',
  trusted: false,
  built_in: false,
  supported_extensions: ['.csv'],
  category: 'data',
});

const AUDIO_TRANSCRIBE = skillMock({
  id: 'audio.transcribe',
  name: 'Audio Transcription',
  version: '0.1.0',
  status: 'future',
  input_kinds: ['.mp3'],
  source_media: 'audio',
  source_kind: 'audio_file',
  loader_name: 'audio.transcribe',
  limitations: ['not_implemented'],
  enabled: false,
  supported_extensions: ['.mp3'],
  category: 'media',
});

async function mockBase(page: Page) {
  await page.route('**/health', (route) => {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });
  await page.route('**/frontend/runtime-config', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'openai_compatible',
        base_url: 'https://api.example.com/v1',
        model: 'test-model',
        api_key_masked: true,
        enabled: true,
        config_source: 'active_config_env',
      }),
    });
  });
  await page.route('**/sources', (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0 }),
    });
  });
  await page.route('**/frontend/media-transcript-config', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: false,
        provider: 'mock',
        api_key_configured: false,
        base_url: '',
        base_url_configured: false,
        model: '',
        timeout_seconds: 60,
        config_source: 'default',
        limitations: [],
      }),
    });
  });
}

test('Settings Sources reads source skills from API', async ({ page }) => {
  await mockBase(page);
  await page.route('**/frontend/source-skills', (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [CSV_EXTRACT, LOCAL_PROJECT_CSV, AUDIO_TRANSCRIBE],
        total: 3,
      }),
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Open settings' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Sources' }).click();

  await expect(page.getByTestId('source-skill-csv.extract')).toContainText('CSV Rows as Text');
  await expect(page.getByTestId('source-skill-local.project_csv')).toContainText('Project CSV Skill');
  await expect(page.getByTestId('source-skill-audio.transcribe')).toContainText('Audio Transcription');
});

test('Settings Sources does not crash when source skill API fails', async ({ page }) => {
  await mockBase(page);
  await page.route('**/frontend/source-skills', (route) => route.fulfill({ status: 500, body: 'failed' }));

  await page.goto('/');
  await page.getByRole('button', { name: 'Open settings' }).click();
  await page.getByRole('button', { name: 'Sources' }).click();

  await expect(page.getByText(/Unable to load source skills|Request failed/)).toBeVisible();
});

test('unsafe manifest validation is shown as rejected', async ({ page }) => {
  await mockBase(page);
  await page.route('**/frontend/source-skills', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) });
    }
    return route.fallback();
  });
  await page.route('**/frontend/source-skills/validate', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: false,
          skill_id: 'local.evil',
          errors: ['Arbitrary entrypoint is not allowed in Skill System v1.1.'],
          warnings: [],
          executable: false,
          reason: 'Manifest failed validation.',
          skill: null,
        }),
      });
    }
    return route.fallback();
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Open settings' }).click();
  await page.getByRole('button', { name: 'Sources' }).click();
  await page.getByTestId('source-skill-manifest').fill('{"id":"local.evil","handler":"csv.extract","entrypoint":"evil.py"}');
  await page.getByRole('button', { name: 'Validate' }).click();

  await expect(page.getByTestId('source-skill-manifest-result')).toContainText('Manifest rejected');
  await expect(page.getByTestId('source-skill-manifest-result')).toContainText('Arbitrary entrypoint');
});

test('local skill enable and disable are shown and functional', async ({ page }) => {
  await mockBase(page);

  let localSkillEnabled = true;
  await page.route('**/frontend/source-skills', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            CSV_EXTRACT,
            { ...LOCAL_PROJECT_CSV, status: localSkillEnabled ? 'local' : 'disabled', enabled: localSkillEnabled },
            AUDIO_TRANSCRIBE,
          ],
          total: 3,
        }),
      });
    }
    return route.fallback();
  });

  let disableCalled = false;
  let enableCalled = false;
  await page.route('**/frontend/source-skills/local.project_csv/disable', (route) => {
    disableCalled = true;
    localSkillEnabled = false;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, skill_id: 'local.project_csv', errors: [], warnings: [], executable: true, reason: 'Disabled.', skill: null }) });
  });
  await page.route('**/frontend/source-skills/local.project_csv/enable', (route) => {
    enableCalled = true;
    localSkillEnabled = true;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, skill_id: 'local.project_csv', errors: [], warnings: [], executable: true, reason: 'Enabled.', skill: null }) });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Open settings' }).click();
  await page.getByRole('button', { name: 'Sources' }).click();

  // Built-in implemented skill should NOT show Disable
  await expect(page.getByTestId('source-skill-csv.extract')).toBeVisible();
  await expect(page.getByTestId('source-skill-toggle-csv.extract')).not.toBeVisible();

  // Future skill should NOT show Enable
  await expect(page.getByTestId('source-skill-audio.transcribe')).toBeVisible();
  await expect(page.getByTestId('source-skill-toggle-audio.transcribe')).not.toBeVisible();

  // Local skill should show Disable
  await expect(page.getByTestId('source-skill-local.project_csv')).toBeVisible();
  await expect(page.getByTestId('source-skill-toggle-local.project_csv')).toContainText('Disable');

  // Click Disable
  await page.getByTestId('source-skill-toggle-local.project_csv').click();
  await expect(page.getByTestId('source-skill-toggle-local.project_csv')).toContainText('Enable');
  expect(disableCalled).toBe(true);

  // Click Enable
  await page.getByTestId('source-skill-toggle-local.project_csv').click();
  await expect(page.getByTestId('source-skill-toggle-local.project_csv')).toContainText('Disable');
  expect(enableCalled).toBe(true);
});
