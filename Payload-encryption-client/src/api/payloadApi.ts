import {
  createAppError,
  type SubmitPayloadRequest,
  type SubmitPayloadResponse,
} from '../types/api';
import { HttpError, httpRequest, NetworkError } from './httpClient';

/** POST /api/v1/secure-payload. Sends only partner_id and the encrypted blob. */
export async function submitEncryptedPayload(
  request: SubmitPayloadRequest,
): Promise<SubmitPayloadResponse> {
  try {
    const data = await httpRequest<SubmitPayloadResponse>('/api/v1/sandbox/secure-payload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        partner_id: request.partner_id,
        encrypted_data: request.encrypted_data,
      }),
    });
    if (typeof data?.transaction_id !== 'string' || data.status !== 'success') {
      throw createAppError('SUBMIT_FAILED');
    }
    return data;
  } catch (error) {
    if (error instanceof HttpError) {
      if (error.status === 429) throw createAppError('RATE_LIMITED');
      if (error.status >= 500) throw createAppError('SERVER_ERROR');
      throw createAppError('SUBMIT_FAILED');
    }
    if (error instanceof NetworkError) throw createAppError('NETWORK_ERROR');
    throw error;
  }
}
