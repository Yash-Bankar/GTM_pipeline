"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { requestContact, requestDraft, type ActionResult } from "@/actions/fit";
import { cn } from "@/components/ui";
import { formatDate } from "@/lib/format";
import type { ContactRequest } from "@/lib/types";

const BUTTON =
  "min-h-11 rounded-lg px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400 disabled:cursor-not-allowed disabled:opacity-40";

const TERMINAL = new Set(["not_found", "failed", "cancelled"]);

function requestCopy(request: ContactRequest | null): { message: string; tone: string } | null {
  if (!request) return null;
  switch (request.status) {
    case "queued":
      return { message: "Contact search queued. The worker will search public sources.", tone: "text-sky-300" };
    case "running":
      return { message: "Searching public sources for contact details…", tone: "text-sky-300" };
    case "found":
      return {
        message: `Public contact found (${request.result_count}). See Public contacts below.`,
        tone: "text-accent-300",
      };
    case "not_found":
      return { message: "No public contact found in searched sources.", tone: "text-amber-glow" };
    case "failed":
      return {
        message: request.error
          ? `Contact search failed: ${request.error}`
          : "Contact search failed.",
        tone: "text-rose-alert",
      };
    case "cancelled":
      return {
        message:
          request.error || "Contact search cancelled because the shortlist was revoked.",
        tone: "text-amber-glow",
      };
    default:
      return null;
  }
}

export function OutreachGates({
  leadId,
  enabled,
  reason,
  contactRequest,
}: {
  leadId: string;
  enabled: boolean;
  reason: string;
  contactRequest: ContactRequest | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [channel, setChannel] = useState<"email" | "instagram_dm">("email");
  const [feedback, setFeedback] = useState<ActionResult | null>(null);

  const gateId = `outreach-gate-${leadId}`;
  const disabled = !enabled || pending;
  const gateProps = enabled
    ? {}
    : { "aria-describedby": gateId, title: reason || "Shortlist this creator first" };
  const searchAgain = Boolean(contactRequest && TERMINAL.has(contactRequest.status));
  const copy = requestCopy(contactRequest);

  function run(task: () => Promise<ActionResult>) {
    startTransition(async () => {
      const result = await task();
      setFeedback(result);
      if (result.ok) router.refresh();
    });
  }

  return (
    <div className="space-y-3 px-5 py-4">
      {!enabled ? (
        <p
          id={gateId}
          role="note"
          className="rounded-lg border border-amber-glow/30 bg-amber-glow/10 px-3 py-2 text-xs text-amber-glow"
        >
          {reason ||
            "Shortlist this creator with current evidence before requesting contact details or drafts."}
        </p>
      ) : null}

      {copy ? (
        <div className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-xs">
          <p className={copy.tone}>{copy.message}</p>
          {contactRequest?.searched_scope ? (
            <p className="mt-1 text-mist-400">
              Searched: {contactRequest.searched_scope}
              {contactRequest.completed_at
                ? ` · ${formatDate(contactRequest.completed_at)}`
                : ""}
            </p>
          ) : null}
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => run(() => requestContact(leadId, searchAgain))}
        disabled={disabled}
        {...gateProps}
        className={cn(BUTTON, "w-full border border-ink-600 text-mist-200 hover:bg-ink-800")}
      >
        {searchAgain ? "Search again" : "Find contact details"}
      </button>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="sm:flex-1">
          <label
            htmlFor={`draft-channel-${leadId}`}
            className="mb-1 block text-xs font-medium text-mist-300"
          >
            Draft channel
          </label>
          <select
            id={`draft-channel-${leadId}`}
            value={channel}
            onChange={(event) =>
              setChannel(event.target.value === "instagram_dm" ? "instagram_dm" : "email")
            }
            disabled={disabled}
            className="field"
          >
            <option value="email">Email</option>
            <option value="instagram_dm">Instagram DM</option>
          </select>
        </div>
        <button
          type="button"
          onClick={() => run(() => requestDraft(leadId, channel))}
          disabled={disabled}
          {...gateProps}
          className={cn(BUTTON, "shrink-0 bg-accent-500 text-ink-950 hover:bg-accent-400")}
        >
          Generate Draft
        </button>
      </div>

      {pending ? <p className="text-xs text-mist-400">Submitting…</p> : null}
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
