export function PageHeader() {
  return (
    <header className="mb-6 text-center">
      <div
        className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-navy-900 text-white"
        aria-hidden="true"
      >
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" strokeLinecap="round" />
        </svg>
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-navy-900 sm:text-3xl">
        Secure Payload Simulator
      </h1>
      <p className="mt-2 text-sm text-slate-600">
        Identity information is encrypted locally in your browser before submission.
      </p>
    </header>
  );
}
