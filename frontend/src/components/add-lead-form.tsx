"use client";

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

export function AddLeadForm() {
  const [state, formAction, pending] = useActionState(addLead, INITIAL);

  return (
    <form action={formAction} className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <input
        name="username"
        className="field sm:flex-1"
        placeholder="@creator or https://instagram.com/creator"
        autoComplete="off"
        spellCheck={false}
        aria-label="Username or Instagram profile URL"
      />
      <button
        type="submit"
        disabled={pending}
        className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-ink-950 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {pending ? "Adding…" : "Add lead"}
      </button>
      {state.status !== "idle" && state.message ? (
        <p className={cn("text-xs sm:basis-full", TONE[state.status])} role="status">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
