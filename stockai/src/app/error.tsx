'use client';

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[route-error] render failed', error);
  }, [error]);
  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-center p-12 text-center">
      <h1 className="text-2xl font-bold">Something failed to render</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {error.message || 'Unexpected client error.'} No financial data was fabricated — retry to reload live state.
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
      >
        Try again
      </button>
    </div>
  );
}
