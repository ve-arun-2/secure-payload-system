/**
 * Pure Web Crypto helpers. No React, no DOM access: safe to run in a Worker.
 * Algorithm is fixed to RSA-OAEP with SHA-256; there is no configurable/legacy fallback.
 */
import type { PlainPayload } from '../types/payload';

const RSA_OAEP_IMPORT_PARAMS: RsaHashedImportParams = { name: 'RSA-OAEP', hash: 'SHA-256' };
const PEM_HEADER = '-----BEGIN PUBLIC KEY-----';
const PEM_FOOTER = '-----END PUBLIC KEY-----';

export function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const CHUNK = 0x8000; // avoids call-stack limits of String.fromCharCode(...bigArray)
  let binary = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

/** Converts an SPKI PEM ("BEGIN PUBLIC KEY") into DER bytes. */
function pemToDer(pem: string): ArrayBuffer {
  const trimmed = pem.trim();
  if (!trimmed.startsWith(PEM_HEADER) || !trimmed.endsWith(PEM_FOOTER)) {
    throw new Error('Invalid PEM public key');
  }
  const body = trimmed.slice(PEM_HEADER.length, trimmed.length - PEM_FOOTER.length).replace(/\s+/g, '');
  return base64ToArrayBuffer(body);
}

/** Imports an SPKI PEM public key as a non-extractable, encrypt-only RSA-OAEP key. */
export async function importPublicKey(pem: string): Promise<CryptoKey> {
  return crypto.subtle.importKey('spki', pemToDer(pem), RSA_OAEP_IMPORT_PARAMS, false, ['encrypt']);
}

/**
 * Serializes the payload to JSON, encrypts it with RSA-OAEP/SHA-256 and returns Base64.
 * The plaintext byte buffer is zero-filled as soon as encryption finishes.
 */
export async function encryptPayload(publicKey: CryptoKey, payload: PlainPayload): Promise<string> {
  const plaintext = new TextEncoder().encode(
    JSON.stringify({
      name: payload.name,
      aadhaar_number: payload.aadhaar_number,
      device_id: payload.device_id,
    }),
  );
  try {
    const cipher = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, plaintext);
    return arrayBufferToBase64(cipher);
  } finally {
    plaintext.fill(0);
  }
}
