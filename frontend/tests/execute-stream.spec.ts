import { expect, Page, test } from '@playwright/test';

function sseBody(events: Array<{ event: string; data: unknown }>) {
  return events.map((item) => `event: ${item.event}\ndata: ${JSON.stringify(item.data)}`).join('\n\n');
}

async function mockRuntimeConfig(page: Page) {
  // Mock /health so the availability probe succeeds
  await page.route('**/health', (route) => {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });

  await page.route('**/frontend/runtime-config', (route) => {
    if (route.request().method() !== 'GET') {
      return route.fallback();
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'openai_compatible',
        base_url: 'https://api.openai.com/v1',
        model: 'gpt-4o-mini',
        api_key_masked: false,
        enabled: false,
        config_source: 'default',
      }),
    });
  });
}

test.describe('execute/stream SSE consumption', () => {
  test.beforeEach(async ({ page }) => {
    await mockRuntimeConfig(page);
  });

  test('completes the full idle to running to completed state transition with artifact rendered', async ({ page }) => {
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: sseBody([
          {
            event: 'run_started',
            data: {
              kind: 'run_started',
              run_id: 'test-run-001',
              event_id: 'e1',
              payload: {},
            },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'test-run-001',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-001',
                  kind: 'text',
                  title: null,
                  content: { text: 'This is a test response from the AI agent.' },
                  metadata: {},
                  citations: [],
                },
              },
            },
          },
          {
            event: 'completed',
            data: {
              kind: 'completed',
              run_id: 'test-run-001',
              event_id: 'e3',
              payload: {},
            },
          },
        ]),
      });
    });

    await page.goto('/');

    const input = page.getByTestId('agent-input');
    await expect(input).toBeVisible();
    await input.fill('What is MindDock?');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText('Please wait while AI prepares your data')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('What is MindDock?')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('This is a test response from the AI agent.')).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('context-mode')).toHaveText('Chat');
  });

  test('displays real progress phase text during execution', async ({ page }) => {
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: sseBody([
          {
            event: 'run_started',
            data: {
              kind: 'run_started',
              run_id: 'test-run-002',
              event_id: 'e1',
              payload: {},
            },
          },
          {
            event: 'progress',
            data: {
              kind: 'progress',
              run_id: 'test-run-002',
              event_id: 'e2',
              payload: { phase: 'resolving_runtime', message: 'Resolving runtime' },
            },
          },
          {
            event: 'progress',
            data: {
              kind: 'progress',
              run_id: 'test-run-002',
              event_id: 'e3',
              payload: { phase: 'retrieving', message: 'Retrieving sources' },
            },
          },
          {
            event: 'completed',
            data: {
              kind: 'completed',
              run_id: 'test-run-002',
              event_id: 'e4',
              payload: {},
            },
          },
        ]),
      });
    });

    await page.goto('/');
    await page.getByTestId('agent-input').fill('What can MindDock do?');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText(/Resolving runtime|Retrieving sources/).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('What can MindDock do?')).toBeVisible({ timeout: 5000 });
  });

  test('shows failed state UI when SSE stream endpoint returns an error', async ({ page }) => {
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal execution error' }),
      });
    });

    await page.goto('/');
    await page.getByTestId('agent-input').fill('What is MindDock?');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText('Failed', { exact: false })).toBeVisible({ timeout: 8000 });
    await expect(page.getByText(/HTTP Error|Stream failed|error/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('agent-submit')).toBeVisible({ timeout: 5000 });
  });
});
