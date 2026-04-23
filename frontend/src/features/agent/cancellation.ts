type CancelRun = (runId: string) => Promise<unknown>;

export interface CancelActiveRunInput {
  runId: string | null;
  controller: AbortController | null;
  cancelRun: CancelRun;
  requestCancel: () => void;
  markCancelled: (message?: string) => void;
  failRun: (message: string) => void;
  setController: (ctrl: AbortController | null) => void;
}

export function cancelActiveRun({
  runId,
  controller,
  cancelRun,
  requestCancel,
  markCancelled,
  failRun,
  setController,
}: CancelActiveRunInput): void {
  requestCancel();

  if (runId) {
    void cancelRun(runId)
      .then(() => {
        markCancelled('Cancellation requested.');
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        failRun(message);
      });
  } else {
    markCancelled('Cancelled before the run started.');
  }

  if (controller) {
    controller.abort();
    setController(null);
  }
}
