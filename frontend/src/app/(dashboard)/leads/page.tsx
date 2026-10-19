import Link from "next/link";

import { AddLeadForm } from "@/components/add-lead-form";
import { LeadFilters } from "@/components/lead-filters";
import { LeadsTable } from "@/components/leads-table";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  StatCard,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";
import type { LeadList, Stats } from "@/lib/types";

const PAGE_SIZE = 25;

type SearchParams = Promise<{ q?: string; status?: string; offset?: string }>;

function pageHref(params: { q?: string; status?: string; offset: number }): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.offset > 0) search.set("offset", String(params.offset));
  const query = search.toString();
  return query ? `/leads?${query}` : "/leads";
}

export default async function LeadsPage({ searchParams }: { searchParams: SearchParams }) {
  await requireSession();

  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : undefined;
  const status = typeof sp.status === "string" ? sp.status : undefined;
  const offset = Math.max(0, Number(sp.offset ?? 0) || 0);

  let leads: LeadList | null = null;
  let stats: Stats | null = null;
  let errorMessage: string | null = null;
  try {
    [leads, stats] = await Promise.all([
      api.listLeads({ q, status, limit: PAGE_SIZE, offset }),
      api.stats(),
    ]);
  } catch (error) {
    errorMessage = error instanceof ApiError ? error.message : "Unexpected error.";
  }

  const header = (
    <PageHeader
      title="Leads"
      description="Every creator captured by the pipeline, with enrichment and processing status."
    />
  );

  if (errorMessage || !leads || !stats) {
    return (
      <>
        {header}
        <ErrorState title="Could not load leads" message={errorMessage ?? "No data returned."} />
        <div className="mt-4">
          <Link
            href={pageHref({ q, status, offset })}
            className="text-sm text-accent-300 underline-offset-2 hover:underline"
          >
            Retry
          </Link>
        </div>
      </>
    );
  }

  const byProgress = stats.leads_by_progress ?? {};
  const researching = (byProgress.queued ?? 0) + (byProgress.running ?? 0);
  const start = leads.total === 0 ? 0 : leads.offset + 1;
  const end = Math.min(leads.offset + leads.items.length, leads.total);

  return (
    <>
      {header}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Needs attention"
          value={byProgress.blocked ?? 0}
          hint="Blocked — see remedy"
        />
        <StatCard
          label="Ready for review"
          value={byProgress.ready ?? 0}
          hint="Research complete"
        />
        <StatCard label="Researching" value={researching} hint="Queued or running" />
        <StatCard label="Total captured" value={stats.leads_total} />
      </div>

      <Card className="mt-5">
        <CardHeader
          title="Add a lead"
          subtitle="Paste a username or an instagram.com profile URL. Duplicates are detected automatically."
        />
        <div className="px-5 py-4">
          <AddLeadForm />
        </div>
      </Card>

      <Card className="mt-5">
        <CardHeader
          title="Pipeline"
          subtitle={leads.total ? `Showing ${start}–${end} of ${leads.total}` : "No leads yet"}
        />
        <div className="border-b border-ink-800 px-5 py-3">
          <LeadFilters q={q} status={status} />
        </div>
        {leads.items.length === 0 ? (
          <EmptyState
            title="No leads match"
            description={q || status ? "Try clearing the filters." : "Add your first lead above."}
          />
        ) : (
          <LeadsTable leads={leads.items} />
        )}
        {leads.total > PAGE_SIZE ? (
          <div className="flex items-center justify-between border-t border-ink-800 px-5 py-3 text-xs text-mist-400">
            <Link
              href={pageHref({ q, status, offset: Math.max(0, offset - PAGE_SIZE) })}
              aria-disabled={offset === 0}
              className={offset === 0 ? "pointer-events-none opacity-40" : "hover:text-mist-100"}
            >
              ← Previous
            </Link>
            <Link
              href={pageHref({ q, status, offset: offset + PAGE_SIZE })}
              aria-disabled={offset + PAGE_SIZE >= leads.total}
              className={
                offset + PAGE_SIZE >= leads.total ? "pointer-events-none opacity-40" : "hover:text-mist-100"
              }
            >
              Next →
            </Link>
          </div>
        ) : null}
      </Card>
    </>
  );
}
