import { useMutation } from '@tanstack/react-query';
import { getPublicKey } from '../api/keysApi';

/**
 * Fetches the RSA public key on demand. A mutation (not a cached query) is used on purpose:
 * the key is fetched fresh for every submission so key rotation is always honoured.
 */
export function usePublicKey() {
  return useMutation({
    mutationKey: ['public-key'],
    mutationFn: getPublicKey,
    gcTime: 0,
  });
}
