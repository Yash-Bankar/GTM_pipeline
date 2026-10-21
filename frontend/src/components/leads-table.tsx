import Link from "next/link";

import { Badge, StatusBadge, VerifiedBadge } from "@/components/ui";
import { followerLabel, humanize } from "@/lib/format";
import type { Lead } from "@/lib/types";

function OptionalBadge({ label, status, empty }: { label: string; status: string; empty: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-mist-400">{label}</span>
      {status ? (
        <Badge
          tone={status === "done" ? "green" : status === "error" || status === "blocked" ? "red" : "neutral"}
        >
          {humanize(status)}
        </Badge>
      ) : (
        <span className="text-xs text-mist-400">{empty}</span>
      )}
    </span>
  );
}

export function LeadsTable({ leads }: { leads: Lead[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-widest text-mist-400">
            <th className="px-5 py-3 font-semibold">Creator</th>
            <th className="px-4 py-3 font-semibold">Followers</th>
            <th className="px-4 py-3 font-semibold">Progress</th>
            <th className="px-4 py-3 font-semibold">Media / Web</th>
            <th className="px-4 py-3 font-semibold">Updated</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => (
            <tr
              key={lead.lead_id}
              className="border-t border-ink-800 transition-colors hover:bg-ink-850/60"
            >
              <td className="px-5 py-3">
                <Link href={`/leads/${lead.lead_id}`} className="group block">
                  <span className="flex items-center gap-1.5 font-medium text-mist-100 group-hover:text-accent-200">
                    @{lead.username}
                    {lead.snapshot?.is_verified ? <VerifiedBadge /> : null}
                  </span>
                  <span className="block text-xs text-mist-400">
                    {lead.full_name || lead.business_category_name || "—"}
                  </span>
                </Link>
              </td>
              <td className="px-4 py-3 font-mono text-mist-200">{followerLabel(lead)}</td>
              <td className="px-4 py-3">
                <div className="flex flex-col gap-1">
                  <StatusBadge status={lead.progress} />
                  {lead.decision_currency === "review_needed" ? (
                    <Badge tone="amber">Review needed</Badge>
                  ) : null}
                  {lead.new_evidence_available ? (
                    <Badge tone="blue">New evidence</Badge>
                  ) : null}
                  {lead.progress === "blocked" && lead.progress_remedy ? (
                    <span className="max-w-xs text-[11px] leading-snug text-rose-alert">
                      {lead.progress_remedy}
                    </span>
                  ) : null}
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-col gap-1">
                  <OptionalBadge
                    label="media"
                    status={lead.media_status}
                    empty={lead.snapshot ? "Not captured" : "—"}
                  />
                  <OptionalBadge label="web" status={lead.website_status} empty="—" />
                </div>
              </td>
              <td className="px-4 py-3 font-mono text-xs text-mist-400">
                {lead.updated_at ? lead.updated_at.slice(0, 16).replace("T", " ") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
