import { Spinner } from './SubmitButton';

export type ProcessingStep = 'fetching-key' | 'encrypting' | 'submitting';

const STEPS: { id: ProcessingStep; label: string }[] = [
  { id: 'fetching-key', label: 'Fetching Public Key...' },
  { id: 'encrypting', label: 'Encrypting Payload...' },
  { id: 'submitting', label: 'Submitting Secure Payload...' },
];

/** Covers the (positioned) parent card while work is in progress. */
export function LoadingOverlay({ step }: { step: ProcessingStep }) {
  const activeIndex = STEPS.findIndex((s) => s.id === step);
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center rounded-lg bg-white/90 px-6 backdrop-blur-sm">
      <Spinner className="h-10 w-10 text-navy-700" />
      <p role="status" aria-live="polite" className="mt-4 text-base font-medium text-navy-900">
        {STEPS[activeIndex].label}
      </p>
      <ol className="mt-4 space-y-1.5 text-xs text-slate-500" aria-hidden="true">
        {STEPS.map((s, i) => (
          <li key={s.id} className={i <= activeIndex ? 'font-medium text-navy-700' : ''}>
            {i < activeIndex ? '✓' : i === activeIndex ? '●' : '○'} {s.label.replace('...', '')}
          </li>
        ))}
      </ol>
    </div>
  );
}
