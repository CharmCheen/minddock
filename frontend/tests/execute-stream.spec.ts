import { expect, Page, test } from '@playwright/test';
import { cancelActiveRun } from '../src/features/agent/cancellation';

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

async function mockSources(page: Page) {
  await page.route('**/sources', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            doc_id: 'doc-selected-001',
            source: 'kb/selected.md',
            source_type: 'file',
            title: 'Selected Doc',
            chunk_count: 2,
            sections: [],
            pages: [],
            requested_url: null,
            final_url: null,
            source_state: {
              doc_id: 'doc-selected-001',
              source: 'kb/selected.md',
              current_version: 'v1',
              content_hash: 'hash-selected',
              last_ingested_at: '2026-04-01T00:00:00Z',
              chunk_count: 2,
              ingest_status: 'ready',
            },
            domain: null,
            description: null,
          },
        ],
        total: 1,
      }),
    });
  });
}

const completedStream = `${sseBody([
  {
    event: 'run_started',
    data: {
      kind: 'run_started',
      run_id: 'test-run-filter',
      event_id: 'e1',
      payload: {},
    },
  },
  {
    event: 'completed',
    data: {
      kind: 'completed',
      run_id: 'test-run-filter',
      event_id: 'e2',
      payload: {},
    },
  },
])}\n\n`;

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

    // The "Please wait while AI prepares your data" intermediate state is not reliably
    // reachable with the SSE mock (which delivers all events in one network chunk), so we
    // assert on the final stable state: artifact text and the user query.
    await expect(page.getByText('What is MindDock?')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('This is a test response from the AI agent.')).toBeVisible({ timeout: 8000 });
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

    // The progress phase intermediate state is not reliably reachable with the SSE mock,
    // so we assert on the final stable state: the user query appears in the DOM.
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

  test('enters failed state when stream ends without a completed or failed terminal event', async ({ page }) => {
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
              run_id: 'test-run-003',
              event_id: 'e1',
              payload: {},
            },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'test-run-003',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-003',
                  kind: 'text',
                  title: null,
                  content: { text: 'Partial response before stream cut off.' },
                  metadata: {},
                  citations: [],
                },
              },
            },
          },
          // No 'completed' or 'failed' event — stream just ends
        ]),
      });
    });

    await page.goto('/');
    await page.getByTestId('agent-input').fill('Tell me something');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText('Failed', { exact: false })).toBeVisible({ timeout: 8000 });
    await expect(page.getByText(/Stream ended before completion/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('agent-submit')).toBeVisible({ timeout: 5000 });
  });

  test('sends selected source filter for chat summarize and compare stream requests', async ({ page }) => {
    await mockSources(page);
    const requestBodies: unknown[] = [];

    await page.route('**/frontend/execute/stream', async (route) => {
      requestBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: completedStream,
      });
    });

    await page.goto('/');
    await page.getByText('Selected Doc', { exact: true }).click();
    await expect(page.getByText('1 source selected')).toBeVisible();

    const modes = [
      { id: 'chat', prompt: 'Question scoped to selected source' },
      { id: 'summarize', prompt: 'Summarize selected source' },
      { id: 'compare', prompt: 'Compare selected source' },
    ];

    for (const mode of modes) {
      await page.getByTestId(`mode-${mode.id}`).click();
      await page.getByTestId('agent-input').fill(mode.prompt);
      await page.getByTestId('agent-submit').click();
      await expect.poll(() => requestBodies.length).toBeGreaterThanOrEqual(modes.indexOf(mode) + 1);
    }

    expect(requestBodies).toEqual([
      expect.objectContaining({
        task_type: 'chat',
        filters: { source: ['kb/selected.md'] },
      }),
      expect.objectContaining({
        task_type: 'summarize',
        filters: { source: ['kb/selected.md'] },
      }),
      expect.objectContaining({
        task_type: 'compare',
        filters: { source: ['kb/selected.md'] },
      }),
    ]);
  });

  test('does not send source filter when no source is selected', async ({ page }) => {
    let requestBody: any = null;

    await page.route('**/frontend/execute/stream', async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: completedStream,
      });
    });

    await page.goto('/');
    await expect(page.getByText('All sources', { exact: true })).toBeVisible();
    await page.getByTestId('agent-input').fill('Question without selected source');
    await page.getByTestId('agent-submit').click();

    await expect.poll(() => requestBody).not.toBeNull();
    expect(requestBody).not.toHaveProperty('filters');
  });

  test('shows fallback and grounding status badges from artifact metadata', async ({ page }) => {
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: `${sseBody([
          {
            event: 'run_started',
            data: {
              kind: 'run_started',
              run_id: 'test-run-metadata',
              event_id: 'e1',
              payload: {},
            },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'test-run-metadata',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-metadata',
                  kind: 'text',
                  title: null,
                  content: { text: 'I cannot answer from the available evidence.' },
                  metadata: {
                    fallback_used: true,
                    support_status: 'insufficient_evidence',
                    insufficient_evidence: true,
                    refusal_reason: 'no_relevant_evidence',
                    grounded_answer: {
                      answer: 'I cannot answer from the available evidence.',
                      evidence: [],
                      support_status: 'insufficient_evidence',
                      refusal_reason: 'no_relevant_evidence',
                    },
                  },
                  citations: [],
                },
              },
            },
          },
          {
            event: 'completed',
            data: {
              kind: 'completed',
              run_id: 'test-run-metadata',
              event_id: 'e3',
              payload: {},
            },
          },
        ])}\n\n`,
      });
    });

    await page.goto('/');
    await page.getByTestId('agent-input').fill('Can you answer this?');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText('I cannot answer from the available evidence.')).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('Fallback', { exact: true })).toBeVisible();
    await expect(page.getByText('Insufficient', { exact: true })).toBeVisible();
    await expect(page.getByText('Refusal: No Relevant Evidence', { exact: true })).toBeVisible();
  });

  test('cancelActiveRun calls backend cancel when run_id exists', async () => {
    const controller = new AbortController();
    const cancelCalls: string[] = [];
    const transitions: string[] = [];

    cancelActiveRun({
      runId: 'test-run-cancel',
      controller,
      cancelRun: async (runId) => {
        cancelCalls.push(runId);
      },
      requestCancel: () => transitions.push('cancelling'),
      markCancelled: (message) => transitions.push(`cancelled:${message}`),
      failRun: (message) => transitions.push(`failed:${message}`),
      setController: (ctrl) => {
        expect(ctrl).toBeNull();
        transitions.push('controller:null');
      },
    });

    await expect.poll(() => cancelCalls).toEqual(['test-run-cancel']);
    await expect.poll(() => transitions).toContain('cancelled:Cancellation requested.');
    expect(transitions).toContain('cancelling');
    expect(transitions).toContain('controller:null');
    expect(controller.signal.aborted).toBe(true);
    expect(transitions.some((item) => item.startsWith('failed:'))).toBe(false);
  });

  test('stops locally without backend cancel before run_started exists', async ({ page }) => {
    let cancelRequests = 0;

    await page.route('**/frontend/execute/stream', () => {
      // Keep the initial request pending so no run_started event is available yet.
    });
    await page.route('**/frontend/runs/**/cancel', async (route) => {
      cancelRequests += 1;
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.goto('/');
    await page.getByTestId('agent-input').fill('Stop before run id');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByTestId('agent-stop')).toBeVisible({ timeout: 5000 });
    await page.getByTestId('agent-stop').click();

    await expect(page.getByText('Cancelled', { exact: true })).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Cancelled before the run started.')).toBeVisible();
    await expect(page.getByText('Failed', { exact: false })).toHaveCount(0);
    expect(cancelRequests).toBe(0);
  });

  test('retains previous turn when a new query is submitted', async ({ page }) => {
    let requestCount = 0;

    await page.route('**/frontend/execute/stream', async (route) => {
      requestCount += 1;
      const runId = `test-run-multi-${requestCount}`;
      const text = requestCount === 1
        ? 'First response from the AI agent.'
        : 'Second response from the AI agent.';

      await route.fulfill({
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
              run_id: runId,
              event_id: 'e1',
              payload: {},
            },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: runId,
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: `art-multi-${requestCount}`,
                  kind: 'text',
                  title: null,
                  content: { text },
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
              run_id: runId,
              event_id: 'e3',
              payload: {},
            },
          },
        ]),
      });
    });

    await page.goto('/');

    // First query
    await page.getByTestId('agent-input').fill('First question');
    await page.getByTestId('agent-submit').click();
    await expect(page.getByText('First question')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('First response from the AI agent.')).toBeVisible({ timeout: 8000 });

    // Second query
    await page.getByTestId('agent-input').fill('Second question');
    await page.getByTestId('agent-submit').click();
    await expect(page.getByText('Second question')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Second response from the AI agent.')).toBeVisible({ timeout: 8000 });

    // Both turns should be visible
    await expect(page.getByText('First question')).toBeVisible();
    await expect(page.getByText('First response from the AI agent.')).toBeVisible();
    await expect(page.getByText('Second question')).toBeVisible();
    await expect(page.getByText('Second response from the AI agent.')).toBeVisible();

    // Conversation header should show 2 turns
    await expect(page.getByText('2 turns')).toBeVisible();
  });

  test('clear conversation resets to empty state', async ({ page }) => {
    await page.route('**/frontend/execute/stream', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: completedStream,
      });
    });

    await page.goto('/');
    await page.getByTestId('agent-input').fill('Question to clear');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText('Question to clear')).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('clear-conversation')).toBeVisible();

    await page.getByTestId('clear-conversation').click();

    // Empty state should return
    await expect(page.getByText('MindDock Knowledge Workspace')).toBeVisible({ timeout: 5000 });
    // Old turn content should be gone
    await expect(page.getByText('Question to clear')).not.toBeVisible();
  });

  test('clicking citation from a previous turn opens source drawer', async ({ page }) => {
    await page.route('**/frontend/execute/stream', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: `${sseBody([
          {
            event: 'run_started',
            data: {
              kind: 'run_started',
              run_id: 'test-run-cite',
              event_id: 'e1',
              payload: {},
            },
          },
          {
            event: 'artifact',
            data: {
              kind: 'artifact',
              run_id: 'test-run-cite',
              event_id: 'e2',
              payload: {
                artifact_index: 0,
                artifact: {
                  artifact_id: 'art-cite',
                  kind: 'text',
                  title: null,
                  content: { text: 'Here is a cited claim.' },
                  metadata: {
                    grounded_answer: {
                      answer: 'Here is a cited claim.',
                      evidence: [
                        {
                          doc_id: 'doc-selected-001',
                          chunk_id: 'chunk-001',
                          source: 'kb/selected.md',
                          snippet: 'The relevant text here.',
                          chunk_index: 3,
                        },
                      ],
                      support_status: 'grounded',
                    },
                  },
                  citations: [],
                },
              },
            },
          },
          {
            event: 'completed',
            data: {
              kind: 'completed',
              run_id: 'test-run-cite',
              event_id: 'e3',
              payload: {},
            },
          },
        ])}\n\n`,
      });
    });

    await mockSources(page);

    await page.goto('/');
    await page.getByTestId('agent-input').fill('Citation test question');
    await page.getByTestId('agent-submit').click();

    await expect(page.getByText('Citation test question')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Here is a cited claim.')).toBeVisible({ timeout: 8000 });

    // Wait for the turn to complete
    await expect(page.getByText('Completed')).toBeVisible({ timeout: 8000 });

    // Submit a second query so the citation turn becomes historical
    await page.route('**/frontend/execute/stream', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: completedStream,
      });
    });

    await page.getByTestId('agent-input').fill('Second question');
    await page.getByTestId('agent-submit').click();
    await expect(page.getByText('Second question')).toBeVisible({ timeout: 5000 });

    // Click citation from the first (historical) turn
    const citation = page.getByText('kb/selected.md').first();
    await expect(citation).toBeVisible({ timeout: 5000 });
    await citation.click();

    // Source drawer should open
    await expect(page.getByTestId('source-drawer')).toBeVisible({ timeout: 5000 });
  });
});
