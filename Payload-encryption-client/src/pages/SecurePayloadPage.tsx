import { useState } from 'react';
import { ErrorBanner } from '../components/ErrorBanner';
import { LoadingOverlay, type ProcessingStep } from '../components/LoadingOverlay';
import { PageHeader } from '../components/PageHeader';
import { SecurePayloadForm } from '../components/SecurePayloadForm';
import { SuccessResult } from '../components/SuccessResult';
import { useEncryptPayload } from '../hooks/useEncryptPayload';
import { usePublicKey } from '../hooks/usePublicKey';
import { useSubmitPayload } from '../hooks/useSubmitPayload';
import type { SecurePayloadFormValues } from '../schemas/securePayloadSchema';
import { AppError, ERROR_MESSAGES } from '../types/api';
import type { SubmissionResult } from '../types/payload';

/** 123456789012 -> 1234XXXX9012 */
function maskAadhaar(aadhaar: string): string {
  return `${aadhaar.slice(0, 4)}XXXX${aadhaar.slice(-4)}`;
}

function toUserMessage(error: unknown): string {
  return error instanceof AppError ? error.message : ERROR_MESSAGES.SUBMIT_FAILED;
}

export function SecurePayloadPage() {
  const keyMutation = usePublicKey();
  const encryptMutation = useEncryptPayload();
  const submitMutation = useSubmitPayload();

  const isFetchingKey = keyMutation.isPending;
  const isEncrypting = encryptMutation.isPending;
  const isSubmitting = submitMutation.isPending;

  // Mutations go idle for an instant between steps; `step` keeps the overlay stable across that gap.
  const [step, setStep] = useState<ProcessingStep | null>(null);
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const isProcessing = step !== null || isFetchingKey || isEncrypting || isSubmitting;
  const submitSuccess = result !== null;

  const resetAll = () => {
    keyMutation.reset();
    encryptMutation.reset();
    submitMutation.reset();
    setResult(null);
    setSubmitError(null);
    setStep(null);
  };

  /** Resolves true on success so the form can wipe its values; on failure values are kept for retry. */
  const handleSubmit = async (values: SecurePayloadFormValues): Promise<boolean> => {
    setSubmitError(null);
    setResult(null);
    const startedAt = performance.now();

    try {
      setStep('fetching-key');
      const key = await keyMutation.mutateAsync();

      setStep('encrypting');
      const encrypted = await encryptMutation.mutateAsync({
        publicKeyPem: key.public_key,
        payload: {
          name: values.name,
          aadhaar_number: values.aadhaar_number,
          device_id: values.device_id,
        },
      });
      // Drop the cached mutation variables (they contain plaintext) right away.
      encryptMutation.reset();

      setStep('submitting');
      const response = await submitMutation.mutateAsync({
        partner_id: values.partner_id,
        encrypted_data: encrypted.encryptedData,
      });

      setResult({
        transactionId: response.transaction_id,
        maskedAadhaar: maskAadhaar(values.aadhaar_number), // only the masked form is retained
        partnerId: values.partner_id,
        encryptionDurationMs: encrypted.durationMs,
        requestDurationMs: performance.now() - startedAt,
      });
      return true;
    } catch (error) {
      encryptMutation.reset();
      setSubmitError(toUserMessage(error));
      return false;
    } finally {
      setStep(null);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-4 py-10">
      <PageHeader />

      <div className="relative rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        {step && <LoadingOverlay step={step} />}

        {submitError && <ErrorBanner message={submitError} onDismiss={() => setSubmitError(null)} />}

        {submitSuccess ? (
          <SuccessResult result={result} onReset={resetAll} />
        ) : (
          <SecurePayloadForm
            disabled={isProcessing}
            isBusy={isProcessing}
            onSubmit={handleSubmit}
            onReset={resetAll}
          />
        )}
      </div>

      <p className="mt-4 text-center text-xs text-slate-500">
        RSA-OAEP (SHA-256) · Encryption runs in a background Web Worker · No data is stored in the browser
      </p>
    </main>
  );
}
