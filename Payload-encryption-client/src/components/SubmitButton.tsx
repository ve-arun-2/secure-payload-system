interface SubmitButtonProps {
  isLoading: boolean;
  label?: string;
  loadingLabel?: string;
}

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export function SubmitButton({
  isLoading,
  label = 'Encrypt & Submit',
  loadingLabel = 'Processing…',
}: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={isLoading}
      aria-busy={isLoading}
      className="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-navy-800 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-navy-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {isLoading && <Spinner />}
      {isLoading ? loadingLabel : label}
    </button>
  );
}
