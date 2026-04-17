import { test, expect, Page } from '@playwright/test';

type SourceItem = {
  doc_id: string;
  title: string;
  category: 'file' | 'url';
  ingest_status: 'ready' | 'processing' | 'failed';
  participation_state?: 'uploaded' | 'indexed' | 'participating' | 'excluded' | null;
  domain?: string | null;
};

function buildSseBody(events: Array<{ event: string; payload?: Record<string, unknown> }>): string {
  return (
    events
    .map(({ event, payload = {} }, index) => {
      const body = {
        kind: event,
        run_id: `test-run-${index + 1}`,
        event_id: `e${index + 1}`,
        payload,
      };
      return `event: ${event}\ndata: ${JSON.stringify(body)}`;
    })
    .join('\n\n') + '\n\n'
  );
}

function mockSources(page: Page, items: SourceItem[], delayMs = 0) {
  return page.route('**/sources', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }

    if (delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items,
        total: items.length,
      }),
    });
  });
}

function rowFor(page: Page, title: string) {
  return page.getByText(title, { exact: true }).locator('xpath=ancestor::div[2]');
}

test.describe('source list participation overlay', () => {
  test('marks participating sources from completed payload', async ({ page }) => {
    await mockSources(page, [
      { doc_id: 'd1', title: 'Doc One', category: 'file', ingest_status: 'ready', participation_state: 'indexed' },
      { doc_id: 'd2', title: 'Doc Two', category: 'file', ingest_status: 'ready', participation_state: 'indexed' },
    ]);

    await page.route('**/frontend/execute/stream', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: buildSseBody([
          { event: 'run_started' },
          {
            event: 'completed',
            payload: {
              participating_sources: [
                { doc_id: 'd1', participation_state: 'participating' },
              ],
            },
          },
        ]),
      });
    });

    await page.goto('/');
    await expect(page.getByText('Doc One')).toBeVisible();
    await expect(page.getByText('Doc Two')).toBeVisible();

    await page.getByPlaceholder('Ask the agent anything...').fill('Question about doc one');
    await page.getByRole('button', { name: 'Send' }).click();

    const docOneRow = rowFor(page, 'Doc One');
    const docTwoRow = rowFor(page, 'Doc Two');

    await expect(docOneRow.getByText(/participating/i)).toBeVisible({ timeout: 5000 });
    await expect(docTwoRow.getByText(/participating/i)).toHaveCount(0);
    await expect(docTwoRow.getByText(/indexed/i)).toBeVisible();
  });

  test('replaces the previous overlay on the next completed payload and clears with empty array', async ({ page }) => {
    await mockSources(page, [
      { doc_id: 'd1', title: 'Doc One', category: 'file', ingest_status: 'ready', participation_state: 'indexed' },
      { doc_id: 'd2', title: 'Doc Two', category: 'file', ingest_status: 'ready', participation_state: 'indexed' },
    ]);

    let streamCount = 0;
    await page.route('**/frontend/execute/stream', async (route) => {
      streamCount += 1;

      const payloads = [
        [{ doc_id: 'd1', participation_state: 'participating' }],
        [{ doc_id: 'd2', participation_state: 'participating' }],
        [],
      ];

      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: buildSseBody([
          { event: 'run_started' },
          {
            event: 'completed',
            payload: {
              participating_sources: payloads[streamCount - 1] ?? [],
            },
          },
        ]),
      });
    });

    await page.goto('/');
    await expect(page.getByText('Doc One')).toBeVisible();

    const queryInput = page.getByPlaceholder('Ask the agent anything...');
    const sendButton = page.getByRole('button', { name: 'Send' });

    await queryInput.fill('round one');
    await sendButton.click();
    const docOneRow = rowFor(page, 'Doc One');
    const docTwoRow = rowFor(page, 'Doc Two');
    await expect(docOneRow.getByText(/participating/i)).toBeVisible({ timeout: 5000 });
    await expect(docTwoRow.getByText(/participating/i)).toHaveCount(0);

    await queryInput.fill('round two');
    await sendButton.click();
    await expect(docTwoRow.getByText(/participating/i)).toBeVisible({ timeout: 5000 });
    await expect(docOneRow.getByText(/participating/i)).toHaveCount(0);
    await expect(docOneRow.getByText(/indexed/i)).toBeVisible();

    await queryInput.fill('round three');
    await sendButton.click();
    await expect(docOneRow.getByText(/participating/i)).toHaveCount(0);
    await expect(docTwoRow.getByText(/participating/i)).toHaveCount(0);
    await expect(docOneRow.getByText(/indexed/i)).toBeVisible();
    await expect(docTwoRow.getByText(/indexed/i)).toBeVisible();
  });

  test('does not crash when participating_sources is missing or sources are still loading', async ({ page }) => {
    await mockSources(page, [
      { doc_id: 'd1', title: 'Doc One', category: 'file', ingest_status: 'ready', participation_state: 'indexed' },
    ], 600);

    const pageErrors: string[] = [];
    page.on('pageerror', (error) => {
      pageErrors.push(error.message);
    });

    await page.route('**/frontend/execute/stream', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: buildSseBody([
          { event: 'run_started' },
          {
            event: 'completed',
            payload: {},
          },
        ]),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Ask the agent anything...').fill('loading case');
    await page.getByRole('button', { name: 'Send' }).click();

    await expect(page.getByText('loading case')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Doc One')).toBeVisible({ timeout: 5000 });
    await expect(rowFor(page, 'Doc One').getByText(/participating/i)).toHaveCount(0);
    expect(pageErrors).toEqual([]);
  });
});
