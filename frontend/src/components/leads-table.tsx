import Link from "next/link";

import { Badge, StatusBadge } from "@/components/ui";
import { formatNumber, humanize } from "@/lib/format";
import type { Lead } from "@/lib/types";

function OptionalBadge({ label, status }: { label: string; status: string }) {
  if (!status) return <span className="text-mist-400">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-mist-400">{label}</span>
      <Badge tone={status === "done" ? "green" : status === "error" ? "red" : status === "blocked" ? "red" : "neutral"}>
        {humanize(status)}
      </Badge>
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
            <th className="px-4 py-3 font-semibold">Status</th>
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
                  <span className="block font-medium text-mist-100 group-hover:text-accent-200">
                    @{lead.username}
                  </span>
                  <span className="block text-xs text-mist-400">
                    {lead.full_name || lead.business_category_name || "—"}
                  </span>
                </Link>
              </td>
              <td className="px-4 py-3 font-mono text-mist-200">{formatNumber(lead.follower_count)}</td>
              <td className="px-4 py-3">
                <StatusBadge status={lead.status} />
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-col gap-1">
                  <OptionalBadge label="media" status={lead.media_status} />
                  <OptionalBadge label="web" status={lead.website_status} />
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
