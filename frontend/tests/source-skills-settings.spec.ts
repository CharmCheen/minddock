import { expect, Page, test } from '@playwright/test';

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
}

test('Settings Sources reads source skills from API', async ({ page }) => {
  await mockBase(page);
  await page.route('**/frontend/source-skills', (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 'csv.extract',
            name: 'CSV Rows as Text',
            kind: 'source',
            version: '1.0.0',
            status: 'implemented',
            description: '',
            input_kinds: ['.csv'],
            output_type: 'SourceLoadResult',
            source_media: 'text',
            source_kind: 'csv_file',
            loader_name: 'csv.extract',
            handler: 'csv.extract',
            capabilities: ['csv_rows_as_text'],
            providers: [],
            limitations: ['no_excel'],
            permissions: ['read_file', 'write_index'],
            safety_notes: [],
            enabled: true,
            origin: 'builtin',
          },
          {
            id: 'local.project_csv',
            name: 'Project CSV Skill',
            kind: 'source',
            version: '0.1.0',
            status: 'local',
            description: '',
            input_kinds: ['.csv'],
            output_type: 'SourceLoadResult',
            source_media: 'text',
            source_kind: 'csv_file',
            loader_name: 'csv.extract',
            handler: 'csv.extract',
            capabilities: ['csv_rows_as_text'],
            providers: [],
            limitations: [],
            permissions: ['read_file'],
            safety_notes: ['uses_builtin_handler'],
            enabled: true,
            origin: 'local',
          },
          {
            id: 'audio.transcribe',
            name: 'Audio Transcription',
            kind: 'source',
            version: '0.1.0',
            status: 'future',
            description: '',
            input_kinds: ['.mp3'],
            output_type: 'SourceLoadResult',
            source_media: 'audio',
            source_kind: 'audio_file',
            loader_name: 'audio.transcribe',
            handler: null,
            capabilities: [],
            providers: [],
            limitations: ['not_implemented'],
            permissions: [],
            safety_notes: [],
            enabled: false,
            origin: 'builtin',
          },
        ],
        total: 3,
      }),
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Open settings' }).click();
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
