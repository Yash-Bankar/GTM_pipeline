import Link from "next/link";

import { AddLeadForm } from "@/components/add-lead-form";
import { CreatorFilters } from "@/components/creator-filters";
import { CreatorsTable } from "@/components/creators-table";
import { LiveRefresh, ViewSwitcher } from "@/components/view-switcher";
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
import { DEFAULT_VIEW, VIEW_HINTS, VIEW_LABELS, normalizeView } from "@/lib/views";

const PAGE_SIZE = 25;

type SearchParams = Promise<{
  q?: string;
  status?: string;
  view?: string;
  sort?: string;
  offset?: string;
}>;

function pageHref(params: {
  q?: string;
  status?: string;
  view?: string;
  sort?: string;
  offset: number;
}): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.view && params.view !== DEFAULT_VIEW) search.set("view", params.view);
  if (params.sort) search.set("sort", params.sort);
  if (params.offset > 0) search.set("offset", String(params.offset));
  const query = search.toString();
  return query ? `/creators?${query}` : "/creators";
}

export default async function CreatorsPage({ searchParams }: { searchParams: SearchParams }) {
  await requireSession();

  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : undefined;
  const status = typeof sp.status === "string" ? sp.status : undefined;
  const view = normalizeView(sp.view);
  const sort = typeof sp.sort === "string" ? sp.sort : undefined;
  const offset = Math.max(0, Number(sp.offset ?? 0) || 0);

  let creators: LeadList | null = null;
  let stats: Stats | null = null;
  let errorMessage: string | null = null;
  try {
    [creators, stats] = await Promise.all([
      api.listLeads({ q, status, view, sort, limit: PAGE_SIZE, offset }),
      api.stats(),
    ]);
  } catch (error) {
    errorMessage = error instanceof ApiError ? error.message : "Unexpected error.";
  }

  const header = (
    <PageHeader
      title="Creators"
      description="Every creator captured by the pipeline. Review the queue, then prepare outreach."
    />
  );

  if (errorMessage || !creators || !stats) {
    return (
      <>
        {header}
        <ErrorState
          title="Could not load creators"
          message={errorMessage ?? "No data returned."}
        />
        <div className="mt-4">
          <Link
            href={pageHref({ q, status, view, sort, offset })}
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
  const start = creators.total === 0 ? 0 : creators.offset + 1;
  const end = Math.min(creators.offset + creators.items.length, creators.total);
  const counts = creators.view_counts ?? {};

  // A pending research job means a visible state will change on its own.
  const hasPending = creators.items.some(
    (lead) => lead.progress === "queued" || lead.progress === "running",
  );

  return (
    <>
      {header}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="To review"
          value={counts.to_review ?? 0}
          hint="Not reviewed or review needed"
        />
        <StatCard
          label="Needs attention"
          value={counts.attention ?? 0}
          hint="Blocked — see remedy"
        />
        <StatCard
          label="Researching"
          value={researching}
          hint="Queued or running"
        />
        <StatCard label="Total captured" value={stats.leads_total} />
      </div>

      <Card className="mt-5">
        <CardHeader
          title="Add creator"
          subtitle="Paste a username or an instagram.com profile URL. Duplicates are detected automatically."
        />
        <div className="px-5 py-4">
          <AddLeadForm />
        </div>
      </Card>

      <Card className="mt-5">
        <CardHeader
          title="Review queue"
          subtitle={`${VIEW_LABELS[view]} · ${
            creators.total ? `Showing ${start}–${end} of ${creators.total}` : "No creators"
          }`}
          actions={<LiveRefresh pending={hasPending} />}
        />

        <div className="space-y-3 border-b border-ink-800 px-5 py-4">
          <div>
            <p
              id="view-switcher-label"
              className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-mist-400"
            >
              Saved view
            </p>
            <div aria-describedby="view-switcher-label">
              <ViewSwitcher active={view} counts={counts} />
            </div>
            <p className="mt-2 text-[11px] text-mist-400">{VIEW_HINTS[view]}</p>
          </div>
          <CreatorFilters q={q} status={status} view={view} sort={sort} />
        </div>

        {creators.items.length === 0 ? (
          <EmptyState
            title={
              view === "to_review"
                ? "No creators to review"
                : `No creators in ${VIEW_LABELS[view].toLowerCase()}`
            }
            description={
              q || status
                ? "Try clearing the filters."
                : view === "to_review"
                  ? "Save a profile with the extension or add a creator."
                  : "Switch to another saved view to see more creators."
            }
            action={
              q || status || view !== DEFAULT_VIEW ? (
                <Link
                  href="/creators"
                  className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
                >
                  Show all creators
                </Link>
              ) : undefined
            }
          />
        ) : (
          <CreatorsTable leads={creators.items} />
        )}

        {creators.total > PAGE_SIZE ? (
          <div className="flex items-center justify-between border-t border-ink-800 px-5 py-3 text-xs text-mist-400">
            <Link
              href={pageHref({ q, status, view, sort, offset: Math.max(0, offset - PAGE_SIZE) })}
              aria-disabled={offset === 0}
              className={offset === 0 ? "pointer-events-none opacity-40" : "hover:text-mist-100"}
            >
              ← Previous
            </Link>
            <span className="font-mono text-[11px]">
              Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.ceil(creators.total / PAGE_SIZE)}
            </span>
            <Link
              href={pageHref({ q, status, view, sort, offset: offset + PAGE_SIZE })}
              aria-disabled={offset + PAGE_SIZE >= creators.total}
              className={
                offset + PAGE_SIZE >= creators.total
                  ? "pointer-events-none opacity-40"
                  : "hover:text-mist-100"
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
