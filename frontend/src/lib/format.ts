/** Small formatting helpers (pure; safe on client and server). */

export function formatNumber(value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function formatDate(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function humanize(value: string): string {
  if (!value) return "—";
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export type Tone = "neutral" | "green" | "amber" | "red" | "blue" | "teal";

export function statusTone(status: string): Tone {
  switch ((status || "").toLowerCase()) {
    case "done":
    case "enriched":
    case "approved":
    case "queued":
      return "green";
    case "running":
    case "retry":
    case "partial":
    case "needs_review":
      return "amber";
    case "error":
    case "not_found":
    case "rejected":
    case "blocked":
      return "red";
    case "none":
    case "new":
      return "neutral";
    default:
      return "blue";
  }
}

export function tierTone(tier: string): Tone {
  switch ((tier || "").toUpperCase()) {
    case "A":
      return "green";
    case "B":
      return "blue";
    case "C":
      return "amber";
    case "D":
      return "red";
    default:
      return "neutral";
  }
}
