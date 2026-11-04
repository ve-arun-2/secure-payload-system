import { useEffect, useRef } from 'react';

interface ErrorBannerProps {
  message: string;
  onDismiss?: () => void;
}

/** Moves focus to itself on mount so keyboard/screen-reader users notice the failure. */
export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, [message]);

  return (
    <div
      ref={ref}
      role="alert"
      tabIndex={-1}
      className="mb-5 flex items-start gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
    >
      <svg viewBox="0 0 24 24" className="mt-0.5 h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5M12 16h.01" strokeLinecap="round" />
      </svg>
      <p className="flex-1">{message}</p>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss error"
          className="rounded px-1 text-red-700 hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
        >
          ×
        </button>
      )}
    </div>
  );
}
