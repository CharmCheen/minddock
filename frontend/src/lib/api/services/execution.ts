import { UnifiedExecutionRequestBody, ClientEvent } from '../../../core/types/api';

interface StreamCallbacks {
  onEvent: (event: ClientEvent) => void;
  onError: (error: Error) => void;
  onDone: () => void;
}

export const ExecutionService = {
  executeStream(input: { query: string, task_type?: string }, callbacks: StreamCallbacks): AbortController {
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    const controller = new AbortController();

    const body: UnifiedExecutionRequestBody = {
      task_type: input.task_type || "chat",
      user_input: input.query,
      top_k: 5,
      output_mode: "text",
      citation_policy: "preferred"
    };

    const startStream = async () => {
      try {
        const response = await fetch(`${baseURL}/frontend/execute/stream`, {
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
              } catch (e) {
                console.warn('Failed to parse SSE payload', data, e);
              }
            }
          }
        }

        
        callbacks.onDone();
      } catch (err: any) {
        if (err.name === 'AbortError') {
          console.log('Stream cancelled by user.');
        } else {
          callbacks.onError(err);
        }
      }
    };

    startStream();
    return controller;
  }
};
