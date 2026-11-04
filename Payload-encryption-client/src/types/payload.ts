/** Values collected by the form. */
export interface SecurePayloadForm {
  partner_id: string;
  name: string;
  aadhaar_number: string;
  device_id: string;
}

/** The sensitive plaintext object that gets encrypted. partner_id is NOT part of it. */
export interface PlainPayload {
  name: string;
  aadhaar_number: string;
  device_id: string;
}

/** Input to the encryption worker. */
export interface EncryptedPayloadRequest {
  publicKeyPem: string;
  payload: PlainPayload;
}

export interface EncryptionResult {
  /** Base64 RSA-OAEP ciphertext. */
  encryptedData: string;
  /** Time spent inside the worker (import key + encrypt + encode). */
  durationMs: number;
}

export type WorkerResponse =
  | ({ ok: true } & EncryptionResult)
  // Deliberately carries no error text: nothing derived from the payload may leave the worker.
  | { ok: false };

/** What the success screen displays. Only the masked Aadhaar is ever retained. */
export interface SubmissionResult {
  transactionId: string;
  maskedAadhaar: string;
  partnerId: string;
  encryptionDurationMs: number;
  requestDurationMs: number;
}
