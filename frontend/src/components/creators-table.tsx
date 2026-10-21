import Link from "next/link";

import { Badge, StatusBadge, VerifiedBadge } from "@/components/ui";
import { followerLabel } from "@/lib/format";
import type { Lead } from "@/lib/types";

/** The fit decision, shown as a badge plus a text label (never colour alone). */
function FitBadge({ lead }: { lead: Lead }) {
  if (lead.fit_status === "rejected") {
    return <Badge tone="red">Rejected</Badge>;
  }
  if (lead.fit_status === "research_more") {
    return <Badge tone="amber">Research more</Badge>;
  }
  if (lead.fit_status === "shortlisted") {
    return lead.decision_currency === "review_needed" ? (
      <Badge tone="amber">Shortlisted · review needed</Badge>
    ) : (
      <Badge tone="green">Shortlisted</Badge>
    );
  }
  return <Badge tone="neutral">Not reviewed</Badge>;
}

/** Contact indicator: a text label plus a badge, never colour alone. */
function ContactIndicator({ types }: { types: string[] }) {
  if (types.length === 0) {
    return <span className="text-xs text-mist-400">No contact</span>;
  }
  const label = types.includes("email") ? "Email" : types.includes("phone") ? "Phone" : "Contact";
  return (
    <Badge tone={types.includes("email") ? "teal" : "neutral"}>{label}</Badge>
  );
}

export function CreatorsTable({ leads }: { leads: Lead[] }) {
  return (
    <>
      {/* Mobile and tablet: a stacked card list. The full table needs more
          room than 768px can give without horizontal scrolling, which would
          hide the decision and contact columns (PRD 6.6 - stable layout at
          360, 390 and 768 CSS pixels). */}
      <ul className="divide-y divide-ink-800 lg:hidden">
        {leads.map((lead) => (
          <li key={lead.lead_id} className="px-4 py-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Link href={`/creators/${lead.lead_id}`} className="group min-w-0">
                <span className="flex items-center gap-1.5 font-medium text-mist-100 group-hover:text-accent-200">
                  @{lead.username}
                  {lead.snapshot?.is_verified ? <VerifiedBadge /> : null}
                </span>
                <span className="block text-xs text-mist-400">
                  {lead.full_name || lead.business_category_name || "—"}
                </span>
              </Link>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <StatusBadge status={lead.progress} />
                <FitBadge lead={lead} />
              </div>
            </div>

            <p className="mt-2 line-clamp-2 text-xs leading-snug text-mist-300">
              {lead.bio || "No bio captured."}
            </p>

            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <div className="flex items-center gap-2">
                <dt className="text-mist-400">Followers</dt>
                <dd className="font-mono text-mist-200">{followerLabel(lead)}</dd>
              </div>
              <div className="flex items-center gap-2">
                <dt className="text-mist-400">Contact</dt>
                <dd>
                  <ContactIndicator types={lead.contact_types ?? []} />
                </dd>
              </div>
              <div className="flex items-center gap-2">
                <dt className="text-mist-400">Observed</dt>
                <dd className="font-mono text-mist-400">
                  {lead.updated_at ? lead.updated_at.slice(0, 10) : "—"}
                </dd>
              </div>
              <div className="flex items-center gap-2">
                <dt className="text-mist-400">New data</dt>
                <dd>
                  {lead.new_evidence_available ? (
                    <Badge tone="blue">New evidence</Badge>
                  ) : (
                    <span className="text-mist-400">—</span>
                  )}
                </dd>
              </div>
            </dl>

            <Link
              href={`/creators/${lead.lead_id}`}
              className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-mist-200 transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
            >
              Review creator
            </Link>
          </li>
        ))}
      </ul>

      {/* Desktop (1024px and up): the full table. */}
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Creators in the selected saved view, with research state, fit decision and contact
            availability.
          </caption>
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-widest text-mist-400">
              <th scope="col" className="px-5 py-3 font-semibold">
                Creator
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Bio
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Followers
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Research
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Decision
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Contact
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Last observed
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
              <tr
                key={lead.lead_id}
                className="border-t border-ink-800 transition-colors hover:bg-ink-850/60"
              >
                <td className="px-5 py-3 align-top">
                  <Link href={`/creators/${lead.lead_id}`} className="group block">
                    <span className="flex items-center gap-1.5 font-medium text-mist-100 group-hover:text-accent-200">
                      @{lead.username}
                      {lead.snapshot?.is_verified ? <VerifiedBadge /> : null}
                    </span>
                    <span className="block text-xs text-mist-400">
                      {lead.full_name || lead.business_category_name || "—"}
                    </span>
                  </Link>
                </td>
                <td className="max-w-[16rem] px-4 py-3 align-top">
                  <p className="line-clamp-2 text-xs leading-snug text-mist-300">
                    {lead.bio || "No bio captured."}
                  </p>
                </td>
                <td className="px-4 py-3 align-top font-mono text-mist-200">
                  {followerLabel(lead)}
                </td>
                <td className="px-4 py-3 align-top">
                  <div className="flex flex-col items-start gap-1">
                    <StatusBadge status={lead.progress} />
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
                <td className="px-4 py-3 align-top">
                  <FitBadge lead={lead} />
                </td>
                <td className="px-4 py-3 align-top">
                  <ContactIndicator types={lead.contact_types ?? []} />
                </td>
                <td className="px-4 py-3 align-top font-mono text-xs text-mist-400">
                  {lead.updated_at ? lead.updated_at.slice(0, 10) : "—"}
                </td>
                <td className="px-4 py-3 align-top">
                  <Link
                    href={`/creators/${lead.lead_id}`}
                    className="inline-block min-h-11 whitespace-nowrap rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-mist-200 transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
                  >
                    Review creator
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
