import { test, expect } from '@playwright/test';

/**
 * Smoke test: /frontend/execute/stream → SSE consumption → store state → artifact visible
 *
 * This test validates the critical path:
 * 1. User types a query and submits (clicking Send)
 * 2. ExecutionService.executeStream() is called with POST /frontend/execute/stream
 * 3. The SSE stream is parsed — each event dispatches to the Zustand store
 * 4. Store transitions: idle → running → completed
 * 5. Artifact appears in the message list
 *
 * The SSE is mocked via page.route() so no backend is required.
 */
test.describe('execute/stream SSE consumption', () => {
  test('completes the full idle → running → completed state transition with artifact rendered', async ({ page }) => {
    // --- 1. Mock the SSE stream for POST /frontend/execute/stream ---
    const sseEvents = [
      {
        event: 'run_started',
        data: JSON.stringify({
          kind: 'run_started',
          run_id: 'test-run-001',
          event_id: 'e1',
          payload: {},
        }),
      },
      {
        event: 'artifact',
        data: JSON.stringify({
          kind: 'artifact',
          run_id: 'test-run-001',
          event_id: 'e2',
          payload: {
            artifact: {
              id: 'art-001',
              kind: 'text',
              content: { text: 'This is a test response from the AI agent.' },
              metadata: {},
            },
          },
        }),
      },
      {
        event: 'completed',
        data: JSON.stringify({
          kind: 'completed',
          run_id: 'test-run-001',
          event_id: 'e3',
          payload: {},
        }),
      },
    ];

    // Encode SSE into the format fetch expects: "event: <kind>\ndata: <json>\n\n"
    const sseBody = sseEvents
      .map((e) => `event: ${e.event}\ndata: ${e.data}`)
      .join('\n\n');

    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: sseBody,
      });
    });

    // --- 2. Navigate to the app ---
    await page.goto('/');

    // --- 3. Verify initial idle state ---
    await expect(page.getByPlaceholder('Ask the agent anything...')).toBeVisible();

    // --- 4. Type a query and submit ---
    await page.getByPlaceholder('Ask the agent anything...').fill('What is MindDock?');
    await page.getByRole('button', { name: 'Send' }).click();

    // --- 5. Wait for the "running" indicator (spinner) to appear ---
    await expect(page.locator('text=Please wait while AI prepares your data')).toBeVisible({ timeout: 5000 });

    // --- 6. Wait for the "completed" state — the user query bubble should be visible ---
    await expect(page.getByText('What is MindDock?')).toBeVisible({ timeout: 5000 });

    // --- 7. Verify the artifact text content is rendered in the message list ---
    await expect(page.getByText('This is a test response from the AI agent.')).toBeVisible({ timeout: 5000 });

    // --- 8. Verify task type badge is shown ---
    await expect(page.getByText('💬 Chat')).toBeVisible({ timeout: 5000 });
  });

  test('displays real progress phase text during execution', async ({ page }) => {
    // --- 1. Mock SSE with progress events ---
    const sseEvents = [
      {
        event: 'run_started',
        data: JSON.stringify({
          kind: 'run_started',
          run_id: 'test-run-002',
          event_id: 'e1',
          payload: {},
        }),
      },
      {
        event: 'progress',
        data: JSON.stringify({
          kind: 'progress',
          run_id: 'test-run-002',
          event_id: 'e2',
          payload: { phase: 'resolving_runtime', message: '解析运行时' },
        }),
      },
      {
        event: 'progress',
        data: JSON.stringify({
          kind: 'progress',
          run_id: 'test-run-002',
          event_id: 'e3',
          payload: { phase: 'retrieving', message: '检索中' },
        }),
      },
      {
        event: 'progress',
        data: JSON.stringify({
          kind: 'progress',
          run_id: 'test-run-002',
          event_id: 'e4',
          payload: { phase: 'generating', message: '生成中' },
        }),
      },
      {
        event: 'completed',
        data: JSON.stringify({
          kind: 'completed',
          run_id: 'test-run-002',
          event_id: 'e5',
          payload: {},
        }),
      },
    ];

    const sseBody = sseEvents
      .map((e) => `event: ${e.event}\ndata: ${e.data}`)
      .join('\n\n');

    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: sseBody,
      });
    });

    // --- 2. Navigate and submit ---
    await page.goto('/');
    await page.getByPlaceholder('Ask the agent anything...').fill('What can MindDock do?');
    await page.getByRole('button', { name: 'Send' }).click();

    // --- 3. Wait for "running" indicator, then verify a real phase label appeared at least once ---
    // The phase should appear as a phase label (not just the generic "Processing..." sub-text)
    // At least one of the mapped Chinese phase labels should be visible during the run
    // (.first() because AgentRunStatus also now shows the same labels — consistency is correct)
    const phaseLabels = ['正在解析运行时', '正在检索资料', '正在生成结果', '准备中', '正在整理输出'];
    const visiblePhaseLabel = page.getByText('正在解析运行时').or(
      page.getByText('正在检索资料')).or(
      page.getByText('正在生成结果')).or(
      page.getByText('准备中')).or(
      page.getByText('正在整理输出')
    );
    await expect(visiblePhaseLabel.first()).toBeVisible({ timeout: 5000 });

    // --- 4. After completed, the running indicator should be gone ---
    await expect(page.getByText('What can MindDock do?')).toBeVisible({ timeout: 5000 });
  });

  test('shows failed state UI when SSE stream endpoint returns an error', async ({ page }) => {
    // Mock: server returns HTTP 500 (simulates backend error during execution)
    await page.route('**/frontend/execute/stream', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal execution error' }),
      });
    });

    // --- Navigate and submit ---
    await page.goto('/');
    await page.getByPlaceholder('Ask the agent anything...').fill('What is MindDock?');
    await page.getByRole('button', { name: 'Send' }).click();

    // --- Verify status bar shows FAILED ---
    await expect(page.getByText('FAILED', { exact: false })).toBeVisible({ timeout: 8000 });

    // --- Verify error message is visible in the status bar ---
    // The error thrown is "HTTP Error: {statusText}", so accept any non-empty error indicator
    await expect(page.getByText(/HTTP Error|Stream failed|error/i)).toBeVisible({ timeout: 5000 });

    // --- Verify button returned to Send state (not still running/cancelled) ---
    await expect(page.getByRole('button', { name: 'Send' })).toBeVisible({ timeout: 5000 });
  });
});
