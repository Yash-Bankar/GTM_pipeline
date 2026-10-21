"use client";

import { useActionState } from "react";

import { logOutreachEvent, type OutreachLogState } from "@/actions/drafts";
import { cn } from "@/components/ui";

const INITIAL: OutreachLogState = { status: "idle" };

const OUTCOMES = [
  { value: "sent", label: "Sent" },
  { value: "replied", label: "Replied" },
  { value: "interested", label: "Interested" },
  { value: "not_interested", label: "Not interested" },
  { value: "follow_up", label: "Follow up" },
];

/** Local datetime-local value for "now", used to pre-populate the sent time. */
function nowLocal(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

export function OutreachLogForm({
  leadId,
  revisionId,
  correctionTarget,
}: {
  leadId: string;
  revisionId: string;
  /** When set, this log corrects that event instead of adding a new one. */
  correctionTarget?: { eventId: string; label: string } | null;
}) {
  const [state, formAction, pending] = useActionState(logOutreachEvent, INITIAL);

  return (
    <form action={formAction} className="space-y-4">
      <input type="hidden" name="leadId" value={leadId} />
      <input type="hidden" name="revisionId" value={revisionId} />
      {correctionTarget ? (
        <input type="hidden" name="corrects_event_id" value={correctionTarget.eventId} />
      ) : null}

      {correctionTarget ? (
        <p className="rounded-lg border border-amber-glow/40 bg-amber-glow/10 px-3 py-2 text-xs text-amber-glow">
          Correcting: {correctionTarget.label}. The earlier entry stays visible in the history.
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label htmlFor="outcome" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
            What happened
          </label>
          <select id="outcome" name="outcome" defaultValue="sent" className="field">
            {OUTCOMES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="channel" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
            Channel
          </label>
          <select id="channel" name="channel" defaultValue="email" className="field">
            <option value="email">Email</option>
            <option value="instagram_dm">Instagram DM</option>
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="sent_at" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          Sent time
        </label>
        <input
          id="sent_at"
          name="sent_at"
          type="datetime-local"
          defaultValue={nowLocal()}
          className="field"
        />
        <p className="text-[11px] text-mist-400">Pre-filled with now — correct it if needed.</p>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="note" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          Note
        </label>
        <textarea
          id="note"
          name="note"
          rows={3}
          defaultValue={correctionTarget?.label ?? ""}
          className="field"
          placeholder="What was sent, or what they replied."
        />
        <p className="text-[11px] text-mist-400">
          A note is required when no draft version is attached.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg border border-accent-600/60 bg-accent-600/15 px-4 py-2 text-sm font-semibold text-accent-200 transition-colors hover:bg-accent-600/25 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Logging…" : correctionTarget ? "Save correction" : "Log sent"}
        </button>
        {state.message ? (
          <span
            className={cn("text-xs", state.status === "saved" ? "text-accent-300" : "text-rose-alert")}
            role="status"
          >
            {state.message}
          </span>
        ) : null}
      </div>
    </form>
  );
}
