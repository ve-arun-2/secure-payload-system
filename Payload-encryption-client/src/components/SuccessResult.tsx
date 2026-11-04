import { useEffect, useRef, useState } from 'react';
import type { SubmissionResult } from '../types/payload';

interface SuccessResultProps {
  result: SubmissionResult;
  onReset: () => void;
}

const formatMs = (ms: number) => `${ms.toFixed(ms < 10 ? 1 : 0)} ms`;

export function SuccessResult({ result, onReset }: SuccessResultProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.transactionId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section aria-labelledby="success-title" className="text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700" aria-hidden="true">
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <h2 id="success-title" ref={headingRef} tabIndex={-1} className="text-xl font-semibold text-navy-900 focus:outline-none">
        Payload submitted securely
      </h2>
      <p className="mt-1 text-sm text-slate-600">Only the encrypted payload was sent to the server.</p>

      <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4 text-left">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Transaction ID</p>
        <div className="mt-1 flex items-center justify-between gap-3">
          <code className="break-all font-mono text-sm text-navy-900">{result.transactionId}</code>
          <button
            type="button"
            onClick={copy}
            className="shrink-0 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-600"
          >
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
          <span className="sr-only" role="status" aria-live="polite">
            {copied ? 'Transaction ID copied to clipboard' : ''}
          </span>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-left text-sm">
        <div className="rounded-md border border-slate-200 p-3">
          <dt className="text-xs text-slate-500">Partner ID</dt>
          <dd className="mt-0.5 break-all font-medium">{result.partnerId}</dd>
        </div>
        <div className="rounded-md border border-slate-200 p-3">
          <dt className="text-xs text-slate-500">Aadhaar (masked)</dt>
          <dd className="mt-0.5 font-mono font-medium">{result.maskedAadhaar}</dd>
        </div>
        <div className="rounded-md border border-slate-200 p-3">
          <dt className="text-xs text-slate-500">Encryption duration</dt>
          <dd className="mt-0.5 font-medium">{formatMs(result.encryptionDurationMs)}</dd>
        </div>
        <div className="rounded-md border border-slate-200 p-3">
          <dt className="text-xs text-slate-500">Total request duration</dt>
          <dd className="mt-0.5 font-medium">{formatMs(result.requestDurationMs)}</dd>
        </div>
      </dl>

      <button
        type="button"
        onClick={onReset}
        className="mt-6 w-full rounded-md bg-navy-800 px-4 py-2.5 text-sm font-medium text-white hover:bg-navy-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-600 focus-visible:ring-offset-2"
      >
        Submit another payload
      </button>
    </section>
  );
}
