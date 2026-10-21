import type { ReactNode } from "react";

import { humanize, statusTone, tierTone, type Tone } from "@/lib/format";

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-ink-600 bg-ink-800 text-mist-300",
  green: "border-accent-600/50 bg-accent-600/15 text-accent-300",
  amber: "border-amber-glow/40 bg-amber-glow/15 text-amber-glow",
  red: "border-rose-alert/40 bg-rose-alert/15 text-rose-alert",
  blue: "border-sky-500/40 bg-sky-500/15 text-sky-300",
  teal: "border-teal-haze/40 bg-teal-haze/15 text-teal-haze",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const value = (status || "").toLowerCase();
  const processing = value === "running";
  const waiting = value === "queued" || value === "retry";
  const finished =
    value === "done" ||
    value === "enriched" ||
    value === "approved" ||
    value === "shortlisted" ||
    value === "ready" ||
    value === "complete" ||
    value === "found";
  return (
    <Badge tone={statusTone(status)}>
      {processing ? (
        <span
          aria-hidden
          className="h-3 w-3 animate-spin rounded-full border-2 border-mist-100/25 border-t-mist-100"
        />
      ) : waiting ? (
        <span
          aria-hidden
          className="h-3 w-3 animate-spin rounded-full border-2 border-dashed border-mist-300/50"
          style={{ animationDuration: "2.4s" }}
        />
      ) : finished ? (
        <span aria-hidden className="text-[11px] leading-none">
          ✓
        </span>
      ) : null}
      {humanize(status)}
    </Badge>
  );
}

export function TierBadge({ tier }: { tier: string }) {
  if (!tier) return <Badge>—</Badge>;
  return <Badge tone={tierTone(tier)}>Tier {tier}</Badge>;
}

/** Blue verified checkmark shown next to a creator handle. */
export function VerifiedBadge({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="Verified account"
      title="Verified account"
      className={cn("inline-flex shrink-0 align-middle text-sky-400", className)}
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden focusable="false">
        <circle cx="12" cy="12" r="10" fill="currentColor" />
        <path
          d="M7 12.4l3.2 3.2L17 8.8"
          fill="none"
          stroke="#0a101c"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-2xl border border-white/10 bg-ink-900/55 shadow-[0_8px_30px_rgba(0,0,0,0.35),0_1px_0_rgba(255,255,255,0.06)_inset] backdrop-blur-xl",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-700/70 px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-mist-100">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-mist-400">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-mist-100">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-sm text-mist-400">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <Card className="px-5 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold text-mist-100">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-mist-400">{hint}</p> : null}
    </Card>
  );
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">{label}</dt>
      <dd className="text-sm text-mist-100">{children}</dd>
    </div>
  );
}

export function ScoreBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const tone = clamped >= 80 ? "bg-accent-500" : clamped >= 60 ? "bg-sky-500" : clamped >= 40 ? "bg-amber-glow" : "bg-rose-alert";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${clamped}%` }} />
      </div>
      <span className="w-10 text-right font-mono text-xs text-mist-300">{clamped}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full border border-ink-600 bg-ink-800 text-mist-400">
        <span aria-hidden className="text-lg">◍</span>
      </div>
      <div>
        <p className="text-sm font-semibold text-mist-100">{title}</p>
        {description ? <p className="mt-1 text-xs text-mist-400">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ title, message }: { title: string; message?: string }) {
  return (
    <Card className="border-rose-alert/30">
      <div className="flex items-start gap-3 px-5 py-5">
        <span aria-hidden className="text-rose-alert">⚠</span>
        <div>
          <p className="text-sm font-semibold text-mist-100">{title}</p>
          {message ? <p className="mt-1 text-xs text-mist-300">{message}</p> : null}
        </div>
      </div>
    </Card>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-mist-300">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-accent-400" />
      {label ? <span className="text-sm">{label}</span> : null}
    </div>
  );
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-5">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-9 animate-pulse rounded-lg bg-ink-800/70" />
      ))}
    </div>
  );
}
