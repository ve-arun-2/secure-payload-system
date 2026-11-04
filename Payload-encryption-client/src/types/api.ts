/** Response of GET /api/v1/keys/public */
export interface PublicKeyResponse {
  algorithm: string;
  public_key: string;
}

/** Body of POST /api/v1/sandbox/secure-payload. Contains ONLY ciphertext. */
export interface SubmitPayloadRequest {
  partner_id: string;
  encrypted_data: string;
}

/** Response of POST /api/v1/secure-payload */
export interface SubmitPayloadResponse {
  status: string;
  transaction_id: string;
}

export type AppErrorCode =
  | 'KEY_FETCH_FAILED'
  | 'ENCRYPTION_FAILED'
  | 'RATE_LIMITED'
  | 'SERVER_ERROR'
  | 'NETWORK_ERROR'
  | 'SUBMIT_FAILED';

/**
 * Application error carrying a stable code and a user-safe message.
 * Never construct it with payload contents.
 */
export class AppError extends Error {
  readonly code: AppErrorCode;

  constructor(code: AppErrorCode, message: string) {
    super(message);
    this.name = 'AppError';
    this.code = code;
  }
}

export const ERROR_MESSAGES: Record<AppErrorCode, string> = {
  KEY_FETCH_FAILED: 'Unable to obtain encryption key.',
  ENCRYPTION_FAILED: 'Failed to encrypt payload.',
  RATE_LIMITED: 'Rate limit exceeded. Please try again later.',
  SERVER_ERROR: 'Unexpected server error.',
  NETWORK_ERROR: 'Unable to reach the server. Check your connection and try again.',
  SUBMIT_FAILED: 'Unable to submit the secure payload.',
};

export function createAppError(code: AppErrorCode): AppError {
  return new AppError(code, ERROR_MESSAGES[code]);
}
