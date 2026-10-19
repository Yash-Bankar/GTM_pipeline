/** Small formatting helpers (pure; safe on client and server). */

import type { CountObservation, Lead } from "./types";

export function formatNumber(value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/**
 * Format a captured count with its precision. Unknown never becomes zero, and
 * approximate values are marked with `~` (PRD A06/A32).
 */
export function formatCount(observation: CountObservation | null | undefined): string {
  if (!observation || observation.value === null || observation.value === undefined) return "Unknown";
  const base = observation.display?.trim() || formatNumber(observation.value);
  return observation.precision === "approximate" ? `~${base}` : base;
}

/** Follower label for a lead, preferring the snapshot's display text/precision. */
export function followerLabel(lead: Pick<Lead, "follower_count" | "status" | "snapshot">): string {
  if (lead.snapshot?.followers) return formatCount(lead.snapshot.followers);
  if (lead.follower_count > 0) return formatNumber(lead.follower_count);
  // An observed enriched zero stays 0; an unenriched count is unknown (PRD A32).
  return lead.status === "enriched" ? "0" : "Unknown";
}

/** Split the stored comma/newline-separated external URL list into an array. */
export function splitUrls(raw: string): string[] {
  return (raw || "")
    .replace(/\n/g, ",")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
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
    case "ready":
    case "done":
    case "enriched":
    case "approved":
    case "found":
      return "green";
    case "running":
    case "retry":
    case "partial":
    case "needs_review":
    case "needs_data":
    case "needs_evidence":
      return "amber";
    case "error":
    case "blocked":
    case "not_found":
    case "rejected":
      return "red";
    case "queued":
    case "review_needed":
      return "blue";
    case "none":
    case "new":
    case "not_reviewed":
    case "not_requested":
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
