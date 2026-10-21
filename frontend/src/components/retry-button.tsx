"use client";

import { useState, useTransition } from "react";

import { retryLead } from "@/actions/leads";
import { cn } from "@/components/ui";

export function RetryButton({ leadId }: { leadId: string }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            setResult(await retryLead(leadId));
          })
        }
        className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 transition-colors hover:border-accent-600/50 hover:text-accent-200 disabled:opacity-50"
      >
        {pending ? "Re-queueing…" : "Re-queue processing"}
      </button>
      {result ? (
        <span className={cn("text-xs", result.ok ? "text-accent-300" : "text-rose-alert")}>
          {result.message}
        </span>
      ) : null}
    </div>
  );
}
