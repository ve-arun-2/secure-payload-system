import { useMutation } from '@tanstack/react-query';
import { encryptInWorker } from '../services/workerService';
import type { EncryptedPayloadRequest, EncryptionResult } from '../types/payload';

/**
 * Encrypts in a Web Worker. `gcTime: 0` plus the caller's `reset()` ensure the mutation
 * variables (which contain plaintext) are not retained in the TanStack cache.
 */
export function useEncryptPayload() {
  return useMutation<EncryptionResult, Error, EncryptedPayloadRequest>({
    mutationKey: ['encrypt-payload'],
    mutationFn: encryptInWorker,
    gcTime: 0,
  });
}
