import { useId, type InputHTMLAttributes } from 'react';
import { useForm, type FieldError, type UseFormRegisterReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  securePayloadDefaults,
  securePayloadSchema,
  type SecurePayloadFormValues,
} from '../schemas/securePayloadSchema';
import { SubmitButton } from './SubmitButton';

interface SecurePayloadFormProps {
  disabled: boolean;
  isBusy: boolean;
  /** Resolves true when the submission succeeded. */
  onSubmit: (values: SecurePayloadFormValues) => Promise<boolean>;
  onReset: () => void;
}

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'name'> {
  label: string;
  hint?: string;
  error?: FieldError;
  registration: UseFormRegisterReturn;
}

function Field({ label, hint, error, registration, ...inputProps }: FieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;

  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        {...registration}
        {...inputProps}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={describedBy}
        className={`mt-1 block w-full rounded-md border bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 disabled:bg-slate-50 disabled:text-slate-500 ${
          error
            ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
            : 'border-slate-300 focus:border-navy-600 focus:ring-navy-100'
        }`}
      />
      {hint && !error && (
        <p id={hintId} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="mt-1 text-xs font-medium text-red-700">
          {error.message}
        </p>
      )}
    </div>
  );
}

export function SecurePayloadForm({ disabled, isBusy, onSubmit, onReset }: SecurePayloadFormProps) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SecurePayloadFormValues>({
    resolver: zodResolver(securePayloadSchema),
    defaultValues: securePayloadDefaults,
    mode: 'onTouched',
    shouldFocusError: true,
  });

  // Clear sensitive values from RHF's internal state once the payload has been accepted.
  const submit = handleSubmit(async (values) => {
    if (await onSubmit(values)) {
      reset(securePayloadDefaults);
    }
  });

  const handleReset = () => {
    reset(securePayloadDefaults);
    onReset();
  };

  return (
    <form onSubmit={submit} noValidate aria-label="Secure payload form" className="space-y-4">
      <fieldset disabled={disabled} className="space-y-4">
        <Field
          label="Partner ID"
          placeholder="partner-123"
          autoComplete="off"
          error={errors.partner_id}
          registration={register('partner_id')}
        />
        <Field
          label="Name"
          placeholder="Full name"
          autoComplete="off"
          error={errors.name}
          registration={register('name')}
        />
        <Field
          label="Mock Aadhaar Number"
          placeholder="123456789012"
          hint="12 digits. Use test data only."
          inputMode="numeric"
          maxLength={12}
          autoComplete="off"
          spellCheck={false}
          error={errors.aadhaar_number}
          registration={register('aadhaar_number')}
        />
        <Field
          label="Device ID"
          placeholder="device-001"
          autoComplete="off"
          error={errors.device_id}
          registration={register('device_id')}
        />
      </fieldset>

      <div className="flex gap-3 pt-2">
        <SubmitButton isLoading={isBusy} label="Encrypt & Submit" loadingLabel="Working…" />
        <button
          type="button"
          onClick={handleReset}
          disabled={disabled}
          className="rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Reset
        </button>
      </div>
    </form>
  );
}
