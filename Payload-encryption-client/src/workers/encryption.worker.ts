/**
 * Dedicated worker: imports the public key and performs RSA-OAEP encryption off the main thread.
 * Errors are reported as a bare `{ ok: false }`, never with messages that could echo input data.
 */
import { encryptPayload, importPublicKey } from '../services/cryptoService';
import type { EncryptedPayloadRequest, WorkerResponse } from '../types/payload';

// The project compiles with the DOM lib (not WebWorker), so describe the worker scope minimally.
interface WorkerScope {
  onmessage: ((event: MessageEvent<EncryptedPayloadRequest>) => void) | null;
  postMessage(message: WorkerResponse): void;
}

const ctx = self as unknown as WorkerScope;

ctx.onmessage = async (event) => {
  const started = performance.now();
  let response: WorkerResponse;
  try {
    const { publicKeyPem, payload } = event.data;
    const key = await importPublicKey(publicKeyPem);
    const encryptedData = await encryptPayload(key, payload);
    response = { ok: true, encryptedData, durationMs: performance.now() - started };
  } catch {
    response = { ok: false };
  }
  ctx.postMessage(response);
};
