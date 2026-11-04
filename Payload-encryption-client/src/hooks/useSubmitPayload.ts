import { useMutation } from '@tanstack/react-query';
import { submitEncryptedPayload } from '../api/payloadApi';
import type { SubmitPayloadRequest, SubmitPayloadResponse } from '../types/api';

export function useSubmitPayload() {
  return useMutation<SubmitPayloadResponse, Error, SubmitPayloadRequest>({
    mutationKey: ['submit-payload'],
    mutationFn: submitEncryptedPayload,
    gcTime: 0,
  });
}
