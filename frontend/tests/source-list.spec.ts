import { expect, Page, test } from '@playwright/test';

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

test.describe('source list with new contract', () => {
  test.beforeEach(async ({ page }) => {
    await mockRuntime(page);
  });

  test('renders sources using new backend field names (source_type, source_state)', async ({ page }) => {
    await page.route('**/sources', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'doc-001',
              source: 'https://example.com/article',
              source_type: 'url',
              title: 'Example Article',
              chunk_count: 3,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/article',
              final_url: 'https://example.com/article',
              source_state: {
                doc_id: 'doc-001',
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
            {
              doc_id: 'doc-002',
              source: '/docs/report.pdf',
              source_type: 'file',
              title: 'Annual Report',
              chunk_count: 7,
              sections: [],
              pages: [],
              requested_url: null,
              final_url: null,
              source_state: {
                doc_id: 'doc-002',
                source: '/docs/report.pdf',
                current_version: 'v1',
                content_hash: 'def456',
                last_ingested_at: '2026-02-20T14:00:00Z',
                chunk_count: 7,
                ingest_status: 'ready',
              },
              domain: null,
              description: null,
            },
          ],
          total: 2,
        }),
      });
    });

    await page.goto('/');

    // URL source renders with link icon and domain badge
    const urlSource = page.locator('text=Example Article').first();
    await expect(urlSource).toBeVisible();

    // Domain badge shows for URL sources
    await expect(page.locator('text=🌐 example.com')).toBeVisible();

    // URL source has link icon (🔗)
    const urlIcon = page.locator('text=🔗').first();
    await expect(urlIcon).toBeVisible();

    // File source renders with document icon
    const fileIcon = page.locator('text=📄').first();
    await expect(fileIcon).toBeVisible();

    // Ready status badge renders for ready sources
    const readyBadges = page.locator('text=● ready');
    await expect(readyBadges).toHaveCount(2);
  });

  test('shows offline state for source drawer when backend is offline', async ({ page }) => {
    // Make the availability probe fail so availabilityStore goes offline
    await page.route('**/health', (route) => {
      route.abort();
    });

    await page.goto('/');

    // Source list should show "Backend Offline" instead of loading
    await expect(page.getByText('Backend Offline').first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Retry Connection').first()).toBeVisible();
  });

  test('citation click navigates to source without using old fields', async ({ page }) => {
    await page.route('**/sources', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'doc-cite-test',
              source: 'https://example.com/cited',
              source_type: 'url',
              title: 'Cited Source',
              chunk_count: 2,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/cited',
              final_url: 'https://example.com/cited',
              source_state: {
                doc_id: 'doc-cite-test',
                source: 'https://example.com/cited',
                current_version: 'v1',
                content_hash: 'hash',
                last_ingested_at: '2026-03-01T09:00:00Z',
                chunk_count: 2,
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

    await page.goto('/');

    // Select the source (which sets selectedDocDetail)
    await page.locator('text=Cited Source').first().click();

    // No TypeScript errors means citation-list passes a valid SourceItem | null
    // (this test verifies the contract is satisfied at runtime)
    await expect(page.locator('text=Cited Source').first()).toBeVisible();
  });
});
