import { z } from 'zod';

/**
 * RSA-2048 with OAEP/SHA-256 can encrypt at most 190 bytes. The JSON envelope is ~46 bytes,
 * the Aadhaar is 12, so the free-text fields are bounded to keep the payload within that limit.
 */
const NAME_MAX_BYTES = 50;
const DEVICE_ID_MAX = 64;

const utf8Length = (value: string): number => new TextEncoder().encode(value).length;

export const securePayloadSchema = z.object({
  partner_id: z
    .string()
    .trim()
    .min(1, 'Partner ID is required')
    .max(64, 'Partner ID must be at most 64 characters'),
  name: z
    .string()
    .trim()
    .min(1, 'Name is required')
    .min(3, 'Name must be at least 3 characters')
    .refine((v) => utf8Length(v) <= NAME_MAX_BYTES, `Name must be at most ${NAME_MAX_BYTES} bytes`),
  aadhaar_number: z
    .string()
    .min(1, 'Aadhaar number is required')
    .regex(/^\d+$/, 'Aadhaar number must contain digits only')
    .length(12, 'Aadhaar number must be exactly 12 digits'),
  device_id: z
    .string()
    .trim()
    .min(1, 'Device ID is required')
    .max(DEVICE_ID_MAX, `Device ID must be at most ${DEVICE_ID_MAX} characters`)
    .regex(/^[A-Za-z0-9._:-]+$/, 'Device ID may contain letters, digits, . _ : - only'),
});

export type SecurePayloadFormValues = z.infer<typeof securePayloadSchema>;

export const securePayloadDefaults: SecurePayloadFormValues = {
  partner_id: '',
  name: '',
  aadhaar_number: '',
  device_id: '',
};
