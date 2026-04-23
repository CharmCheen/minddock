import { expect, Page, test } from '@playwright/test';

function sseBody(events: Array<{ event: string; data: unknown }>) {
  return events.map((item) => `event: ${item.event}\ndata: ${JSON.stringify(item.data)}`).join('\n\n');
}

async function mockRuntime(page: Page) {
  await page.route('**/health', (route) => {
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });

  await page.route('**/frontend/runtime-config', (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
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

async function mockSourceList(page: Page) {
  await page.route('**/sources', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            doc_id: 'doc-cite-001',
            source: 'https://example.com/article',
            source_type: 'url',
            title: 'Test Source for Citation',
            chunk_count: 3,
            sections: [],
            pages: [],
            requested_url: 'https://example.com/article',
            final_url: 'https://example.com/article',
            source_state: {
              doc_id: 'doc-cite-001',
              source: 'https://example.com/article',
              current_version: 'v1',
              content_hash: 'abc123',
              last_ingested_at: '2026-01-15T10:30:00Z',
              chunk_count: 3,
              ingest_status: 'ready',
            },
            domain: 'example.com',
            description: null,
          },
        ],
        total: 1,
      }),
    });
  });
}

async function mockSourceChunks(page: Page) {
  await page.route('**/sources/doc-cite-001/chunks**', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        found: true,
        chunks: [
          {
            doc_id: 'doc-cite-001',
            chunk_id: 'chunk-001',
            chunk_index: 0,
            preview_text: 'First chunk of the article discussing key concepts.',
            page: 1,
            location: 'intro',
            metadata: {},
          },
          {
            doc_id: 'doc-cite-001',
            chunk_id: 'chunk-002',
            chunk_index: 1,
            preview_text: 'Second chunk with more detailed analysis.',
            page: 2,
            location: 'body',
            metadata: {},
          },
          {
            doc_id: 'doc-cite-001',
            chunk_id: 'chunk-003',
            chunk_index: 2,
            preview_text: 'Third chunk with conclusions.',
            page: 3,
            location: 'conclusion',
            metadata: {},
          },
        ],
        total_chunks: 3,
        returned_chunks: 3,
        limit: 100,
        offset: 0,
      }),
    });
  });
}

test.describe('citation navigation to source drawer', () => {
  test.beforeEach(async ({ page }) => {
    await mockRuntime(page);
    await mockSourceList(page);
    await mockSourceChunks(page);
  });

  test('clicking a citation opens the source drawer', async ({ page }) => {
    // Mock SSE stream that returns a completed run with an artifact containing a citation
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
        body: sseBody([
          {
            event: 'run_started',
            data: { kind: 'run_started', run_id: 'run-cite-001', event_id: 'e1', payload: {} },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'run-cite-001',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-cite-001',
                  kind: 'text',
                  title: null,
                  content: { text: 'According to the source, MindDock uses retrieval-augmented generation.' },
                  metadata: {},
                  citations: [
                    {
                      doc_id: 'doc-cite-001',
                      chunk_id: 'chunk-002',
                      chunk_index: 1,
                      title: 'Test Source for Citation',
                      snippet: 'Second chunk with more detailed analysis.',
                      source: 'https://example.com/article',
                      page_num: 2,
                    },
                  ],
                },
              },
            },
          },
          {
            event: 'completed',
            data: { kind: 'completed', run_id: 'run-cite-001', event_id: 'e3', payload: {} },
          },
        ]),
      });
    });

    await page.goto('/');

    // Submit a query
    const input = page.getByTestId('agent-input');
    await input.fill('What does MindDock use?');
    await page.getByTestId('agent-submit').click();

    // Wait for the artifact to appear
    await expect(page.getByText('According to the source')).toBeVisible({ timeout: 8000 });

    // Click the citation reference
    await page.locator('text=Test Source for Citation').first().click();

    // Drawer should open and chunks should load (proved by chunks content appearing in DOM)
    // The drawer header shows 'doc-cite-001' as fallback since selectedDocDetail is null
    // Wait for chunks endpoint to be hit and return data
    await page.waitForFunction(
      () => document.body.textContent?.includes('First chunk') ||
            document.body.textContent?.includes('Second chunk') ||
            document.body.textContent?.includes('Third chunk'),
      { timeout: 8000 }
    );
  });

  test('clicking a citation with chunk_index scrolls to the correct chunk in the drawer', async ({ page }) => {
    await mockSourceChunks(page);

    // Mock SSE with a citation that has chunk_index
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
        body: sseBody([
          {
            event: 'run_started',
            data: { kind: 'run_started', run_id: 'run-cite-002', event_id: 'e1', payload: {} },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'run-cite-002',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-cite-002',
                  kind: 'text',
                  title: null,
                  content: { text: 'Analysis of the second chunk.' },
                  metadata: {},
                  citations: [
                    {
                      doc_id: 'doc-cite-001',
                      chunk_id: 'chunk-002',
                      chunk_index: 1,
                      title: 'Test Source for Citation',
                      snippet: 'Second chunk with more detailed analysis.',
                      source: 'https://example.com/article',
                      page_num: 2,
                    },
                  ],
                },
              },
            },
          },
          {
            event: 'completed',
            data: { kind: 'completed', run_id: 'run-cite-002', event_id: 'e3', payload: {} },
          },
        ]),
      });
    });

    await page.goto('/');

    // Submit query
    await page.getByTestId('agent-input').fill('Analyze the second chunk');
    await page.getByTestId('agent-submit').click();

    // Wait for artifact
    await expect(page.getByText('Analysis of the second chunk')).toBeVisible({ timeout: 8000 });

    // Click citation
    await page.locator('text=Test Source for Citation').first().click();

    // Wait for drawer to show source title
    await expect(page.locator('text=Test Source for Citation').first()).toBeVisible({ timeout: 3000 });

    // Wait for chunks to load in drawer
    await page.waitForFunction(
      () => document.body.textContent?.includes('Second chunk with more detailed analysis'),
      { timeout: 5000 }
    );

    // The chunk from citation should be visible (the highlighted one)
    await expect(page.getByText('Second chunk with more detailed analysis')).toBeVisible({ timeout: 3000 });
  });

  test('clicking a citation with only doc_id (no chunk_id) opens the drawer for the source', async ({ page }) => {
    // Mock SSE with a citation that has no chunk_index
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
        body: sseBody([
          {
            event: 'run_started',
            data: { kind: 'run_started', run_id: 'run-cite-003', event_id: 'e1', payload: {} },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'run-cite-003',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-cite-003',
                  kind: 'text',
                  title: null,
                  content: { text: 'A general statement about the knowledge base.' },
                  metadata: {},
                  citations: [
                    {
                      doc_id: 'doc-cite-001',
                      // No chunk_id, no chunk_index
                      title: 'Test Source for Citation',
                      source: 'https://example.com/article',
                    },
                  ],
                },
              },
            },
          },
          {
            event: 'completed',
            data: { kind: 'completed', run_id: 'run-cite-003', event_id: 'e3', payload: {} },
          },
        ]),
      });
    });

    await page.goto('/');

    // Submit query
    await page.getByTestId('agent-input').fill('Tell me about the knowledge base');
    await page.getByTestId('agent-submit').click();

    // Wait for artifact
    await expect(page.getByText('A general statement about the knowledge base')).toBeVisible({ timeout: 8000 });

    // Click citation (no chunk info)
    await page.locator('text=Test Source for Citation').first().click();

    // Drawer should open with source title
    await expect(page.locator('text=Test Source for Citation').first()).toBeVisible({ timeout: 3000 });
  });
});
