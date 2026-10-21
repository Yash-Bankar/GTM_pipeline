"use client";

import { useState } from "react";

import { OutreachLogForm } from "@/components/outreach-log-form";
import { cn } from "@/components/ui";
import { formatDate } from "@/lib/format";
import type { OutreachEvent } from "@/lib/types";

const OUTCOME_LABELS: Record<string, string> = {
  sent: "Sent",
  replied: "Replied",
  interested: "Interested",
  not_interested: "Not interested",
  follow_up: "Follow up",
};

function describe(event: OutreachEvent): string {
  const outcome = OUTCOME_LABELS[event.outcome] ?? event.outcome;
  const channel = event.channel === "instagram_dm" ? "DM" : "Email";
  const time = event.sent_at ? formatDate(event.sent_at) : "no time";
  return `${outcome} · ${channel} · ${time}`;
}

export function OutreachHistory({
  leadId,
  revisionId,
  events,
}: {
  leadId: string;
  revisionId: string;
  events: OutreachEvent[];
}) {
  const [correcting, setCorrecting] = useState<string | null>(null);

  const target = events.find((event) => event.event_id === correcting) ?? null;

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-ink-700 bg-ink-850/40 px-4 py-4">
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          Log an outcome
        </h3>
        <p className="mt-1 text-xs text-mist-400">
          Manual entries only. Nothing is dispatched from here.
        </p>
        <div className="mt-3">
          <OutreachLogForm
            leadId={leadId}
            revisionId={revisionId}
            correctionTarget={
              target
                ? { eventId: target.event_id, label: describe(target) }
                : null
            }
          />
        </div>
        {target ? (
          <button
            type="button"
            onClick={() => setCorrecting(null)}
            className="mt-3 text-xs font-semibold text-mist-300 underline underline-offset-4 hover:text-mist-100"
          >
            Cancel correction
          </button>
        ) : null}
      </div>

      <div>
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          History
        </h3>
        {events.length === 0 ? (
          <p className="mt-2 text-xs text-mist-400">
            Nothing logged yet. Copying or exporting a draft never marks it as sent.
          </p>
        ) : (
          <ol className="mt-2 space-y-2">
            {events.map((event) => {
              const isCorrection = event.source === "manually_logged_correction";
              return (
                <li
                  key={event.event_id}
                  className={cn(
                    "rounded-lg border px-3 py-2",
                    isCorrection
                      ? "border-amber-glow/30 bg-amber-glow/5"
                      : "border-ink-700 bg-ink-850/30",
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium text-mist-100">
                      {describe(event)}
                    </span>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                        isCorrection
                          ? "border-amber-glow/40 text-amber-glow"
                          : "border-ink-600 text-mist-400",
                      )}
                    >
                      {isCorrection ? "Correction" : "Manually logged"}
                    </span>
                  </div>
                  {event.note ? (
                    <p className="mt-1 text-xs text-mist-300">{event.note}</p>
                  ) : null}
                  {event.actor ? (
                    <p className="mt-1 text-[11px] text-mist-500">by {event.actor}</p>
                  ) : null}
                  {!isCorrection ? (
                    <button
                      type="button"
                      onClick={() => setCorrecting(event.event_id)}
                      className="mt-1 text-[11px] font-semibold text-mist-300 underline underline-offset-4 hover:text-mist-100"
                    >
                      Correct this entry
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
