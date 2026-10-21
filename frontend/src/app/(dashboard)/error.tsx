"use client";

import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="rounded-2xl border border-rose-alert/30 bg-ink-900/70 p-8">
      <p className="text-sm font-semibold text-mist-100">Something went wrong</p>
      <p className="mt-1 text-xs text-mist-400">
        {error.message || "The dashboard hit an unexpected error."}
      </p>
      <button
        type="button"
        onClick={reset}
        className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400mt-4 rounded-lg border border-ink-600 px-4 py-2 text-xs font-semibold text-mist-200 hover:bg-ink-800"
      >
        Try again
      </button>
    </div>
  );
}
