import { getApiBaseUrl } from '../client';
import { UnifiedExecutionRequestBody, ClientEvent, CancelRunResponse } from '../../../core/types/api';

interface StreamCallbacks {
  onEvent: (event: ClientEvent) => void;
  onError: (error: Error, isNetworkError?: boolean) => void;
  onDone: () => void;
}

interface ExecutionInput {
  query: string;
  task_type?: string;
  sources?: string[];
  top_k?: number;
  citation_policy?: 'required' | 'preferred' | 'none';
  summarize_mode?: 'basic' | 'map_reduce';
}

function joinApiPath(baseUrl: string, path: string): string {
  if (!baseUrl) return path;
  return `${baseUrl.replace(/\/$/, '')}${path}`;
}

const isAbortError = (err: unknown): boolean =>
  err instanceof Error && err.name === 'AbortError';

const isBrowserNetworkError = (err: unknown): boolean =>
  err instanceof TypeError && err.message.toLowerCase().includes('failed to fetch');

export const ExecutionService = {
  async cancelRun(runId: string): Promise<CancelRunResponse> {
    const baseURL = getApiBaseUrl();
    const response = await fetch(joinApiPath(baseURL, `/frontend/runs/${encodeURIComponent(runId)}/cancel`), {
      method: 'POST',
      headers: { 'Accept': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Cancel failed: ${response.statusText}`);
    }

    return response.json();
  },

  executeStream(input: ExecutionInput, callbacks: StreamCallbacks): AbortController {
    const baseURL = getApiBaseUrl();
    const controller = new AbortController();

    const body: UnifiedExecutionRequestBody = {
      task_type: input.task_type || "chat",
      user_input: input.query,
      top_k: input.top_k ?? 5,
      output_mode: "text",
      citation_policy: input.citation_policy || "preferred"
    };

    if (input.sources && input.sources.length > 0) {
      body.filters = { source: input.sources };
    }

    if (input.summarize_mode) {
      body.task_options = { mode: input.summarize_mode };
    }

    const startStream = async () => {
      try {
        const response = await fetch(joinApiPath(baseURL, '/frontend/execute/stream'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP Error: ${response.statusText}`);
        }

        if (!response.body) {
          throw new Error('ReadableStream not supported in this browser.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let terminalSeen = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split('\n\n');

          buffer = chunks.pop() || ''; // Keep the incomplete chunk in buffer

          for (const chunk of chunks) {
            if (!chunk.trim()) continue;

            const lines = chunk.split('\n');
            let event = '';
            let data = '';

            for (const line of lines) {
              if (line.startsWith('event:')) {
                event = line.replace('event:', '').trim();
              } else if (line.startsWith('data:')) {
                data += line.replace('data:', '').trim();
              }
            }

            if (event && data) {
              try {
                const parsedData = JSON.parse(data);
                // Backend sends ClientEventResponseItem: { kind, payload, run_id, event_id, ... }
                // Frontend ClientEvent expects: { event: kind, data: payload, run_id }
                callbacks.onEvent({
                  event: parsedData.kind as any,
                  data: parsedData.payload,
                  run_id: parsedData.run_id,
                });
                if (parsedData.kind === 'completed' || parsedData.kind === 'failed') {
                  terminalSeen = true;
                }
              } catch (e) {
                console.warn('Failed to parse SSE payload', data, e);
              }
            }
          }
        }

        if (!terminalSeen) {
          callbacks.onError(new Error('Stream ended before completion'), false);
          return;
        }

        callbacks.onDone();
      } catch (err: unknown) {
        if (isAbortError(err)) {
          // HMR / user cancel — silent, no UI error
          return;
        }
        const isNetErr = isBrowserNetworkError(err);
        const message = err instanceof Error ? err.message : String(err);
        callbacks.onError(new Error(message), isNetErr);
      }
    };

    startStream();
    return controller;
  }
};
