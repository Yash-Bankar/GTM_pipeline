"use client";

import { useState, useTransition } from "react";

import { retryAi } from "@/actions/leads";
import { cn } from "@/components/ui";

export function RetryAiButton({ leadId }: { leadId: string }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            setResult(await retryAi(leadId));
          })
        }
        className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400inline-flex items-center gap-2 rounded-lg border border-teal-haze/50 bg-teal-haze/10 px-3 py-1.5 text-xs font-semibold text-teal-haze transition-colors hover:bg-teal-haze/20 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? (
          <>
            <span
              aria-hidden
              className="h-3 w-3 animate-spin rounded-full border-2 border-teal-haze/40 border-t-teal-haze"
            />
            Re-queueing AI…
          </>
        ) : (
          "Re-process AI Jobs Only"
        )}
      </button>
      {result ? (
        <span className={cn("text-xs", result.ok ? "text-accent-300" : "text-rose-alert")} role="status">
          {result.message}
        </span>
      ) : null}
    </div>
  );
}
