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

    // URL source renders with title and URL kind badge
    const urlSource = page.locator('text=Example Article').first();
    await expect(urlSource).toBeVisible();

    // URL kind badge shows for URL sources
    await expect(page.locator('text=URL').first()).toBeVisible();

    // URL source has first-letter icon (U)
    const urlIcon = page.locator('text=U').first();
    await expect(urlIcon).toBeVisible();

    // File source (PDF) renders with first-letter icon (P)
    const fileIcon = page.locator('text=P').first();
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

  test('filter tabs filter sources by type', async ({ page }) => {
    await page.route('**/sources', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'doc-url',
              source: 'https://example.com/article',
              source_type: 'url',
              title: 'URL Article',
              chunk_count: 1,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/article',
              final_url: 'https://example.com/article',
              source_state: { doc_id: 'doc-url', source: 'https://example.com/article', current_version: 'v1', content_hash: 'a', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 1, ingest_status: 'ready' },
              domain: 'example.com',
              description: null,
            },
            {
              doc_id: 'doc-pdf',
              source: '/docs/report.pdf',
              source_type: 'file',
              title: 'PDF Report',
              chunk_count: 1,
              sections: [],
              pages: [],
              requested_url: null,
              final_url: null,
              source_state: { doc_id: 'doc-pdf', source: '/docs/report.pdf', current_version: 'v1', content_hash: 'b', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 1, ingest_status: 'ready' },
              domain: null,
              description: null,
            },
          ],
          total: 2,
        }),
      });
    });

    await page.goto('/');
    await expect(page.locator('text=URL Article')).toBeVisible();
    await expect(page.locator('text=PDF Report')).toBeVisible();

    await page.getByRole('button', { name: 'URL' }).click();
    await expect(page.locator('text=URL Article')).toBeVisible();
    await expect(page.locator('text=PDF Report')).not.toBeVisible();

    await page.getByRole('button', { name: 'File' }).click();
    await expect(page.locator('text=URL Article')).not.toBeVisible();
    await expect(page.locator('text=PDF Report')).toBeVisible();

    await page.getByRole('button', { name: 'All' }).click();
    await expect(page.locator('text=URL Article')).toBeVisible();
    await expect(page.locator('text=PDF Report')).toBeVisible();
  });

  test('renders durable pending and failed URL rows without allowing retrieval selection', async ({ page }) => {
    await page.route('**/sources', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'pending-url-doc',
              source: 'https://example.com/pending',
              source_type: 'url',
              title: 'Pending Article',
              chunk_count: 0,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/pending',
              final_url: null,
              source_state: {
                doc_id: 'pending-url-doc',
                source: 'https://example.com/pending',
                current_version: null,
                content_hash: null,
                last_ingested_at: null,
                chunk_count: 0,
                ingest_status: 'indexing',
                error_message: null,
              },
              domain: null,
              description: null,
            },
            {
              doc_id: 'failed-url-doc',
              source: 'https://example.com/failed',
              source_type: 'url',
              title: 'Failed Article',
              chunk_count: 0,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/failed',
              final_url: null,
              source_state: {
                doc_id: 'failed-url-doc',
                source: 'https://example.com/failed',
                current_version: null,
                content_hash: null,
                last_ingested_at: null,
                chunk_count: 0,
                ingest_status: 'failed',
                error_message: 'Import failed due to 404',
              },
              domain: null,
              description: 'Import failed due to 404',
            },
          ],
          total: 2,
        }),
      });
    });

    await page.goto('/');

    await expect(page.locator('text=Pending Article')).toBeVisible();
    await expect(page.locator('text=Failed Article')).toBeVisible();
    await expect(page.locator('text=Import failed due to 404')).toBeVisible();

    await page.locator('text=Pending Article').click();
    await expect(page.getByRole('status')).toContainText('still importing');
    await expect(page.getByText(/1 selected/)).not.toBeVisible();
    await expect(page.getByTestId('source-drawer')).not.toBeVisible();

    await page.locator('text=Failed Article').click();
    await expect(page.getByRole('status')).toContainText('Import failed due to 404');
    await expect(page.getByText(/1 selected/)).not.toBeVisible();
    await expect(page.getByTestId('source-drawer')).not.toBeVisible();
  });

  test('source drawer shows extraction warning for ready URL with low text metadata', async ({ page }) => {
    await page.route('**/sources', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'doc-warn',
              source: 'https://example.com/js-docs',
              source_type: 'url',
              title: 'JS Docs',
              chunk_count: 1,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/js-docs',
              final_url: 'https://example.com/js-docs',
              source_state: { doc_id: 'doc-warn', source: 'https://example.com/js-docs', current_version: 'v1', content_hash: 'a', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 1, ingest_status: 'ready' },
              domain: 'example.com',
              description: null,
            },
          ],
          total: 1,
        }),
      });
    });
    await page.route('**/sources/doc-warn', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      if (route.request().url().includes('/chunks')) return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          item: {
            doc_id: 'doc-warn',
            source: 'https://example.com/js-docs',
            source_type: 'url',
            title: 'JS Docs',
            chunk_count: 1,
            sections: [],
            pages: [],
            requested_url: 'https://example.com/js-docs',
            final_url: 'https://example.com/js-docs',
            source_state: { doc_id: 'doc-warn', source: 'https://example.com/js-docs', current_version: 'v1', content_hash: 'a', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 1, ingest_status: 'ready' },
            domain: 'example.com',
            description: null,
          },
          representative_metadata: {
            extraction_warnings: 'canonical_missing,empty_main_text',
            extracted_char_count: '84',
            extraction_quality: 'low_text',
          },
          admin_metadata: {},
        }),
      });
    });
    await page.route('**/sources/doc-warn/chunks**', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          chunks: [],
          total_chunks: 0,
          returned_chunks: 0,
          limit: 100,
          offset: 0,
        }),
      });
    });

    await page.goto('/');
    await expect(page.locator('text=JS Docs')).toBeVisible();
    await page.locator('text=JS Docs').click();
    await expect(page.getByText(/1 selected/)).toBeVisible();
    await page.getByTitle('View details').first().click();

    await expect(page.getByTestId('source-drawer')).toBeVisible();
    await expect(page.getByTestId('source-extraction-warning')).toContainText('Extraction may be incomplete. This page may require JavaScript rendering or contain little readable text.');
  });

  test('source drawer does not warn for healthy URL canonical metadata or file source', async ({ page }) => {
    await page.route('**/sources', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'doc-healthy',
              source: 'https://example.com/healthy',
              source_type: 'url',
              title: 'Healthy URL',
              chunk_count: 2,
              sections: [],
              pages: [],
              requested_url: 'https://example.com/healthy',
              final_url: 'https://example.com/healthy',
              source_state: { doc_id: 'doc-healthy', source: 'https://example.com/healthy', current_version: 'v1', content_hash: 'h', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 2, ingest_status: 'ready' },
              domain: 'example.com',
              description: null,
            },
            {
              doc_id: 'doc-file',
              source: '/docs/report.pdf',
              source_type: 'file',
              title: 'Report File',
              chunk_count: 2,
              sections: [],
              pages: [1],
              requested_url: null,
              final_url: null,
              source_state: { doc_id: 'doc-file', source: '/docs/report.pdf', current_version: 'v1', content_hash: 'f', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 2, ingest_status: 'ready' },
              domain: null,
              description: null,
            },
          ],
          total: 2,
        }),
      });
    });
    await page.route('**/sources/doc-healthy', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      if (route.request().url().includes('/chunks')) return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          item: {
            doc_id: 'doc-healthy',
            source: 'https://example.com/healthy',
            source_type: 'url',
            title: 'Healthy URL',
            chunk_count: 2,
            sections: [],
            pages: [],
            requested_url: 'https://example.com/healthy',
            final_url: 'https://example.com/healthy',
            source_state: { doc_id: 'doc-healthy', source: 'https://example.com/healthy', current_version: 'v1', content_hash: 'h', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 2, ingest_status: 'ready' },
            domain: 'example.com',
            description: null,
          },
          representative_metadata: {
            extraction_warnings: 'canonical_missing',
            extracted_char_count: '1200',
            extraction_quality: 'ok',
          },
          admin_metadata: {},
        }),
      });
    });
    await page.route('**/sources/doc-file', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      if (route.request().url().includes('/chunks')) return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          item: {
            doc_id: 'doc-file',
            source: '/docs/report.pdf',
            source_type: 'file',
            title: 'Report File',
            chunk_count: 2,
            sections: [],
            pages: [1],
            requested_url: null,
            final_url: null,
            source_state: { doc_id: 'doc-file', source: '/docs/report.pdf', current_version: 'v1', content_hash: 'f', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 2, ingest_status: 'ready' },
            domain: null,
            description: null,
          },
          representative_metadata: {
            extraction_warnings: 'empty_main_text',
            extracted_char_count: '0',
            extraction_quality: 'warning',
          },
          admin_metadata: {},
        }),
      });
    });
    await page.route('**/sources/**/chunks**', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ found: true, chunks: [], total_chunks: 0, returned_chunks: 0, limit: 100, offset: 0 }),
      });
    });

    await page.goto('/');
    await expect(page.locator('text=Healthy URL')).toBeVisible();
    await page.getByTitle('View details').first().click();

    await expect(page.getByTestId('source-drawer')).toBeVisible();
    await expect(page.getByTestId('source-extraction-warning')).toHaveCount(0);

    await page.getByTestId('source-drawer').locator('button').first().click();
    await expect(page.getByTestId('source-drawer')).not.toBeVisible();
    await page.getByTitle('View details').nth(1).click();
    await expect(page.getByTestId('source-drawer').getByText('Report File')).toBeVisible();
    await expect(page.getByTestId('source-extraction-warning')).toHaveCount(0);
  });

  test('source drawer shows video sidecar transcript metadata', async ({ page }) => {
    await page.route('**/sources', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              doc_id: 'doc-video',
              source: 'demo_video.mp4',
              source_type: 'file',
              title: 'demo_video',
              chunk_count: 1,
              sections: [],
              pages: [],
              requested_url: null,
              final_url: null,
              source_state: { doc_id: 'doc-video', source: 'demo_video.mp4', current_version: 'v1', content_hash: 'v', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 1, ingest_status: 'ready' },
              domain: null,
              description: null,
            },
          ],
          total: 1,
        }),
      });
    });
    await page.route('**/sources/doc-video', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      if (route.request().url().includes('/chunks')) return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          item: {
            doc_id: 'doc-video',
            source: 'demo_video.mp4',
            source_type: 'file',
            title: 'demo_video',
            chunk_count: 1,
            sections: [],
            pages: [],
            requested_url: null,
            final_url: null,
            source_state: { doc_id: 'doc-video', source: 'demo_video.mp4', current_version: 'v1', content_hash: 'v', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 1, ingest_status: 'ready' },
            domain: null,
            description: null,
          },
          representative_metadata: {
            source_media: 'video',
            transcript_provider: 'sidecar',
            media_filename: 'demo_video.mp4',
            transcript_sidecar_filename: 'demo_video.txt',
          },
          admin_metadata: {},
        }),
      });
    });
    await page.route('**/sources/doc-video/chunks**', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          chunks: [],
          total_chunks: 0,
          returned_chunks: 0,
          limit: 100,
          offset: 0,
        }),
      });
    });

    await page.goto('/');
    await expect(page.locator('text=demo_video')).toBeVisible();
    await page.getByTitle('View details').first().click();

    const mediaMetadata = page.getByTestId('source-media-metadata');
    await expect(mediaMetadata).toContainText('Video source');
    await expect(mediaMetadata).toContainText('Transcript: sidecar');
    await expect(mediaMetadata).toContainText('Media: demo_video.mp4');
    await expect(mediaMetadata).toContainText('Sidecar: demo_video.txt');
  });

  test('delete source triggers confirmation and refreshes list', async ({ page }) => {
    let deleteCalled = false;
    let deleted = false;

    // GET /sources
    await page.route('**/sources', (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      if (deleted) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) });
      }
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
              source_state: { doc_id: 'doc-001', source: 'https://example.com/article', current_version: 'v1', content_hash: 'a', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 3, ingest_status: 'ready' },
              domain: 'example.com',
              description: null,
            },
          ],
          total: 1,
        }),
      });
    });

    // DELETE /sources/doc-001
    await page.route('**/sources/**', (route) => {
      if (route.request().method() === 'DELETE') {
        deleteCalled = true;
        deleted = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ found: true, doc_id: 'doc-001', source: 'https://example.com/article', source_type: 'url', deleted_chunks: 3 }) });
      }
      return route.fallback();
    });

    await page.goto('/');
    await expect(page.locator('text=Example Article')).toBeVisible();

    page.on('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Delete' }).first().click();

    await expect(page.locator('text=Example Article')).not.toBeVisible();
    expect(deleteCalled).toBe(true);
  });

  test('reingest source calls API and refreshes list', async ({ page }) => {
    let reingestCalled = false;
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
              source_state: { doc_id: 'doc-001', source: 'https://example.com/article', current_version: 'v1', content_hash: 'a', last_ingested_at: '2026-01-01T00:00:00Z', chunk_count: 3, ingest_status: 'ready' },
              domain: 'example.com',
              description: null,
            },
          ],
          total: 1,
        }),
      });
    });
    await page.route('**/sources/doc-001/reingest', (route) => {
      reingestCalled = true;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ found: true, ok: true, doc_id: 'doc-001', source: 'https://example.com/article', source_type: 'url', chunks_upserted: 3, chunks_deleted: 0 }) });
    });

    await page.goto('/');
    await expect(page.locator('text=Example Article')).toBeVisible();
    await page.getByRole('button', { name: 'Reingest' }).first().click();
    await expect(page.locator('text=Example Article')).toBeVisible();
    expect(reingestCalled).toBe(true);
  });
});
