/** Thin fetch wrapper. Only status codes leave this module; response/request bodies are never logged. */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const TIMEOUT_MS = 15_000;

export class HttpError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`HTTP ${status}`);
    this.name = 'HttpError';
    this.status = status;
  }
}

export class NetworkError extends Error {
  constructor() {
    super('Network error');
    this.name = 'NetworkError';
  }
}

export async function httpRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init.headers ?? {}) },
      credentials: 'omit',
      cache: 'no-store',
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new NetworkError();
  }

  if (!response.ok) {
    throw new HttpError(response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new HttpError(response.status);
  }
}
