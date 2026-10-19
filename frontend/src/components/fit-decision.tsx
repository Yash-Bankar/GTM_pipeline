"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { decideFit, type ActionResult, type FitAction } from "@/actions/fit";
import { Badge, cn } from "@/components/ui";
import { formatDate, humanize, type Tone } from "@/lib/format";

const STATUS_TONE: Record<string, Tone> = {
  approved: "green",
  rejected: "red",
  needs_evidence: "amber",
  not_reviewed: "neutral",
};

const BUTTON_BASE =
  "min-h-11 rounded-lg px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400 disabled:cursor-not-allowed disabled:opacity-50";

export function FitDecision({
  leadId,
  fitStatus,
  fitNote,
  fitDecidedAt,
}: {
  leadId: string;
  fitStatus: string;
  fitNote: string;
  fitDecidedAt: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState<ActionResult | null>(null);
  const status = fitStatus || "not_reviewed";

  function submit(action: FitAction) {
    if (action === "reject" && !note.trim()) {
      setFeedback({ ok: false, message: "A rejection note is required." });
      return;
    }
    startTransition(async () => {
      const result = await decideFit({ leadId, action, note });
      setFeedback(result);
      if (result.ok) {
        setNote("");
        router.refresh();
      }
    });
  }

  return (
    <div className="space-y-3 px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONE[status] ?? "neutral"}>{humanize(status)}</Badge>
        {fitDecidedAt ? (
          <span className="text-xs text-mist-400">Decided {formatDate(fitDecidedAt)}</span>
        ) : (
          <span className="text-xs text-mist-400">No decision recorded yet</span>
        )}
      </div>

      {fitNote ? (
        <p className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-xs text-mist-300">
          Note: {fitNote}
        </p>
      ) : null}

      <label htmlFor={`fit-note-${leadId}`} className="block text-xs font-medium text-mist-300">
        Decision note <span className="text-mist-400">(required to reject)</span>
      </label>
      <textarea
        id={`fit-note-${leadId}`}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={2}
        maxLength={2000}
        placeholder="Why this decision?"
        className="field min-h-16 resize-y"
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => submit("approve")}
          disabled={pending}
          className={cn(BUTTON_BASE, "bg-accent-500 text-ink-950 hover:bg-accent-400")}
        >
          Approve Fit
        </button>
        <button
          type="button"
          onClick={() => submit("need_evidence")}
          disabled={pending}
          className={cn(
            BUTTON_BASE,
            "border border-amber-glow/40 bg-amber-glow/10 text-amber-glow hover:bg-amber-glow/20",
          )}
        >
          Need Evidence
        </button>
        <button
          type="button"
          onClick={() => submit("reject")}
          disabled={pending}
          className={cn(
            BUTTON_BASE,
            "border border-rose-alert/40 bg-rose-alert/10 text-rose-alert hover:bg-rose-alert/20",
          )}
        >
          Reject
        </button>
      </div>

      {pending ? <p className="text-xs text-mist-400">Saving decision…</p> : null}
      {feedback ? (
        <p
          role="status"
          className={cn("text-xs", feedback.ok ? "text-accent-300" : "text-rose-alert")}
        >
          {feedback.message}
        </p>
      ) : null}
    </div>
  );
}
