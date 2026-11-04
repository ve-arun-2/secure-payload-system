import { createAppError } from '../types/api';
import type { EncryptedPayloadRequest, EncryptionResult, WorkerResponse } from '../types/payload';

/**
 * Runs one encryption in a fresh dedicated worker and terminates it afterwards, so no
 * plaintext lingers in a long-lived worker heap. Rejects with AppError('ENCRYPTION_FAILED').
 */
export function encryptInWorker(request: EncryptedPayloadRequest): Promise<EncryptionResult> {
  return new Promise<EncryptionResult>((resolve, reject) => {
    let worker: Worker;
    try {
      worker = new Worker(new URL('../workers/encryption.worker.ts', import.meta.url), {
        type: 'module',
      });
    } catch {
      reject(createAppError('ENCRYPTION_FAILED'));
      return;
    }

    const timeout = window.setTimeout(() => finish(() => reject(createAppError('ENCRYPTION_FAILED'))), 30_000);

    const finish = (settle: () => void) => {
      window.clearTimeout(timeout);
      worker.onmessage = null;
      worker.onerror = null;
      worker.onmessageerror = null;
      worker.terminate();
      settle();
    };

    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const data = event.data;
      if (data.ok) {
        finish(() => resolve({ encryptedData: data.encryptedData, durationMs: data.durationMs }));
      } else {
        finish(() => reject(createAppError('ENCRYPTION_FAILED')));
      }
    };
    worker.onerror = (event) => {
      event.preventDefault();
      finish(() => reject(createAppError('ENCRYPTION_FAILED')));
    };
    worker.onmessageerror = () => finish(() => reject(createAppError('ENCRYPTION_FAILED')));

    worker.postMessage(request);
  });
}
