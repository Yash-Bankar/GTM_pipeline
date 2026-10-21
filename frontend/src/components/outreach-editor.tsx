"use client";

import { useActionState } from "react";

import { saveOutreach, type OutreachState } from "@/actions/outreach";
import { cn } from "@/components/ui";

const INITIAL: OutreachState = { status: "idle" };

const BUTTONS = [
  { value: "NEEDS_REVIEW", label: "Save draft", className: "border-ink-600 text-mist-200 hover:bg-ink-800" },
  { value: "APPROVED", label: "Approve", className: "border-accent-600/60 bg-accent-600/15 text-accent-200 hover:bg-accent-600/25" },
  { value: "REJECTED", label: "Reject", className: "border-rose-alert/50 bg-rose-alert/10 text-rose-alert hover:bg-rose-alert/20" },
];

export function OutreachEditor({
  leadId,
  initial,
}: {
  leadId: string;
  initial: { subject: string; body: string; dmBody: string; status: string };
}) {
  const [state, formAction, pending] = useActionState(saveOutreach, INITIAL);

  return (
    <form action={formAction} className="space-y-5">
      <input type="hidden" name="leadId" value={leadId} />

      <div className="space-y-1.5">
        <label htmlFor="subject" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          Email subject
        </label>
        <input id="subject" name="subject" defaultValue={initial.subject} className="field" />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="body" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          Email body
        </label>
        <textarea id="body" name="body" defaultValue={initial.body} rows={11} className="field font-mono text-[13px] leading-relaxed" />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="dm_body" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          Instagram DM
        </label>
        <textarea id="dm_body" name="dm_body" defaultValue={initial.dmBody} rows={4} className="field font-mono text-[13px] leading-relaxed" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {BUTTONS.map((button) => (
          <button
            key={button.value}
            type="submit"
            name="status"
            value={button.value}
            disabled={pending}
            className={cn("focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400", 
              "rounded-lg border px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
              button.className,
            )}
          >
            {button.label}
          </button>
        ))}
        {state.status !== "idle" && state.message ? (
          <span
            className={cn(
              "text-xs",
              state.status === "saved" ? "text-accent-300" : "text-rose-alert",
            )}
            role="status"
          >
            {state.message}
          </span>
        ) : null}
      </div>

      <p className="text-[11px] text-mist-400">
        Drafts are never sent. Approve or reject for internal tracking only.
      </p>
    </form>
  );
}
