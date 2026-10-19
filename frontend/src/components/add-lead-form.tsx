"use client";

import Link from "next/link";
import { useActionState } from "react";

import { addLead, type AddLeadState } from "@/actions/leads";
import { cn } from "@/components/ui";

const INITIAL: AddLeadState = { status: "idle" };

const TONE: Record<AddLeadState["status"], string> = {
  idle: "",
  created: "text-accent-300",
  duplicate: "text-amber-glow",
  error: "text-rose-alert",
};

const FEEDBACK_ID = "add-lead-feedback";

export function AddLeadForm() {
  const [state, formAction, pending] = useActionState(addLead, INITIAL);
  const invalid = Boolean(state.invalid);
  const showFeedback = state.status !== "idle" && Boolean(state.message);

  return (
    <form action={formAction} className="flex flex-col gap-3">
      {/* Input + button share one row; feedback is a separate full-width row so
          it can never collapse the input (QA09). */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="sm:min-w-[15rem] sm:flex-1">
          <label htmlFor="add-lead-username" className="mb-1 block text-xs font-medium text-mist-300">
            Instagram username or profile URL
          </label>
          <input
            id="add-lead-username"
            name="username"
            className="field"
            placeholder="@creator or https://instagram.com/creator"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={invalid || undefined}
            aria-describedby={showFeedback ? FEEDBACK_ID : undefined}
          />
        </div>
        <button
          type="submit"
          disabled={pending}
          className="min-h-11 shrink-0 rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-ink-950 transition-colors hover:bg-accent-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Adding…" : "Add lead"}
        </button>
      </div>

      {showFeedback ? (
        <p id={FEEDBACK_ID} className={cn("text-xs", TONE[state.status])} role="status">
          {state.message}
          {state.status === "created" && state.leadId ? (
            <>
              {" "}
              <Link href={`/leads/${state.leadId}`} className="underline underline-offset-2">
                View creator
              </Link>
            </>
          ) : null}
        </p>
      ) : null}
    </form>
  );
}
