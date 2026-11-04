import { createAppError, type PublicKeyResponse } from '../types/api';
import { httpRequest } from './httpClient';

/** GET /api/v1/keys/public. Any failure or malformed response becomes KEY_FETCH_FAILED. */
export async function getPublicKey(): Promise<PublicKeyResponse> {
  let data: PublicKeyResponse;
  try {
    data = await httpRequest<PublicKeyResponse>('/api/v1/keys/public');
  } catch {
    throw createAppError('KEY_FETCH_FAILED');
  }

  const valid =
    data !== null &&
    typeof data === 'object' &&
    typeof data.algorithm === 'string' &&
    data.algorithm.toUpperCase() === 'RSA' &&
    typeof data.public_key === 'string' &&
    data.public_key.includes('-----BEGIN PUBLIC KEY-----');

  if (!valid) {
    throw createAppError('KEY_FETCH_FAILED');
  }
  return data;
}
