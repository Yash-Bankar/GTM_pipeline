import Link from "next/link";
import type { ReactNode } from "react";

import { Badge, Card, CardHeader, ErrorState, PageHeader, cn } from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, type Tone } from "@/lib/format";
import { requireSession } from "@/lib/session";
import type { IntegrationsStatus } from "@/lib/types";

function WorkerDot({ state }: { state: IntegrationsStatus["worker"] }) {
  if (state === "active") {
    return (
      <span className="relative flex h-3 w-3" aria-hidden>
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />
        <span className="relative inline-flex h-3 w-3 rounded-full bg-accent-500" />
      </span>
    );
  }
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex h-3 w-3 rounded-full",
        state === "stale" ? "bg-amber-glow" : "bg-mist-400",
      )}
    />
  );
}

function StatusCard({
  title,
  value,
  detail,
  badge,
  dot,
}: {
  title: string;
  value: string;
  detail: string;
  badge: { label: string; tone: Tone };
  dot?: ReactNode;
}) {
  return (
    <Card className="px-5 py-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
          {title}
        </p>
        {dot}
      </div>
      <p className="mt-2 text-lg font-semibold text-mist-100">{value}</p>
      <div className="mt-1">
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>
      <p className="mt-2 text-xs text-mist-400">{detail}</p>
    </Card>
  );
}

const WORKER_COPY: Record<
  IntegrationsStatus["worker"],
  { value: string; badge: string; tone: Tone; detail: string }
> = {
  active: { value: "Active", badge: "Healthy", tone: "green", detail: "Polling the job queue." },
  stale: {
    value: "Stale",
    badge: "Check",
    tone: "amber",
    detail: "No heartbeat in the last 60 seconds.",
  },
  stopped: {
    value: "Stopped",
    badge: "Stopped",
    tone: "neutral",
    detail: "No worker heartbeat has been recorded.",
  },
};

export default async function SettingsPage() {
  await requireSession();

  let status: IntegrationsStatus | null = null;
  let errorMessage: string | null = null;
  try {
    status = await api.integrationsStatus();
  } catch (error) {
    errorMessage = error instanceof ApiError ? error.message : "Unexpected error.";
  }

  const worker = status ? WORKER_COPY[status.worker] : null;
  const rules: Array<{ label: string; description: string; value: string; tone: Tone }> =
    status
      ? [
          {
            label: "Snapshot-first capture",
            description: "A captured DOM snapshot is enough to enrich a lead.",
            value: "Active",
            tone: "green",
          },
          {
            label: "Contact masking",
            description: "Email/phone patterns are masked before AI intake.",
            value: "Active",
            tone: "green",
          },
          {
            label: "Reviewed draft preservation",
            description:
              "NEEDS_REVIEW, APPROVED and REJECTED drafts are never overwritten by a rerun.",
            value: "Active",
            tone: "green",
          },
          {
            label: "HikerAPI fallback",
            description:
              status.hikerapi === "configured"
                ? "Used only when no snapshot exists."
                : "Disabled — snapshot-only capture.",
            value: status.hikerapi === "configured" ? "Optional" : "Disabled",
            tone: status.hikerapi === "configured" ? "teal" : "neutral",
          },
          {
            label: "AI drafts",
            description: "Drafts are stored NEEDS_REVIEW; nothing is sent automatically.",
            value: "Review only",
            tone: "blue",
          },
          {
            label: "Worker stale threshold",
            description: "A heartbeat older than 60 seconds is reported as stale.",
            value: "60s",
            tone: "neutral",
          },
        ]
      : [];

  return (
    <>
      <PageHeader
        title="Settings"
        description="System health and configuration for the GTM pipeline."
        actions={
          <Link
            href="/settings"
            className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
          >
            Refresh
          </Link>
        }
      />

      {errorMessage || !status || !worker ? (
        <ErrorState
          title="Could not load system status"
          message={errorMessage ?? "No data returned."}
        />
      ) : (
        <>
          <section aria-labelledby="integrations-heading">
            <h2
              id="integrations-heading"
              className="mb-3 text-sm font-semibold text-mist-100"
            >
              System Integrations
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatusCard
                title="Background Worker"
                value={worker.value}
                badge={{ label: worker.badge, tone: worker.tone }}
                detail={
                  status.worker_last_beat_at
                    ? `Last heartbeat ${formatDate(status.worker_last_beat_at)}`
                    : worker.detail
                }
                dot={<WorkerDot state={status.worker} />}
              />
              <StatusCard
                title="Database"
                value={status.database === "healthy" ? "Healthy" : "Unreachable"}
                badge={{
                  label: status.database === "healthy" ? "Healthy" : "Unreachable",
                  tone: status.database === "healthy" ? "green" : "red",
                }}
                detail="PostgreSQL — the single source of truth."
              />
              <StatusCard
                title="Gemini AI"
                value={status.gemini === "configured" ? "Configured" : "Disabled"}
                badge={{
                  label: status.gemini === "configured" ? "Configured" : "Missing key",
                  tone: status.gemini === "configured" ? "green" : "neutral",
                }}
                detail="Dossiers and outreach drafts (review-only)."
                dot={
                  <span
                    aria-hidden
                    className={
                      status.gemini === "configured"
                        ? "text-base font-bold text-accent-300"
                        : "text-base text-mist-400"
                    }
                  >
                    {status.gemini === "configured" ? "✓" : "—"}
                  </span>
                }
              />
              <StatusCard
                title="HikerAPI"
                value={status.hikerapi === "configured" ? "Configured" : "Disabled"}
                badge={{
                  label: status.hikerapi === "configured" ? "Configured" : "Missing key",
                  tone: status.hikerapi === "configured" ? "green" : "neutral",
                }}
                detail="Optional fallback for profile and media data."
                dot={
                  <span
                    aria-hidden
                    className={
                      status.hikerapi === "configured"
                        ? "text-base font-bold text-accent-300"
                        : "text-base text-mist-400"
                    }
                  >
                    {status.hikerapi === "configured" ? "✓" : "—"}
                  </span>
                }
              />
            </div>
          </section>

          <Card className="mt-6">
            <CardHeader
              title="Pipeline Rules"
              subtitle="Behaviors enforced by the backend, not editable here."
            />
            <dl className="divide-y divide-ink-800">
              {rules.map((rule) => (
                <div
                  key={rule.label}
                  className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <dt className="text-sm font-medium text-mist-100">{rule.label}</dt>
                    <dd className="mt-0.5 text-xs text-mist-400">{rule.description}</dd>
                  </div>
                  <Badge tone={rule.tone}>{rule.value}</Badge>
                </div>
              ))}
            </dl>
          </Card>

          <p className="mt-4 text-xs text-mist-400">
            Provider credentials are configured server-side and are never displayed here.
          </p>
        </>
      )}
    </>
  );
}
