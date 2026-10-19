import Link from "next/link";

import { Card, CardHeader, EmptyState, ErrorState, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { requireSession } from "@/lib/session";
import type { OutreachList } from "@/lib/types";

const STATUS_OPTIONS = ["", "NEEDS_REVIEW", "APPROVED", "REJECTED"];

type SearchParams = Promise<{ status?: string }>;

export default async function OutreachPage({ searchParams }: { searchParams: SearchParams }) {
  await requireSession();
  const sp = await searchParams;
  const status = typeof sp.status === "string" ? sp.status : undefined;

  let data: OutreachList | null = null;
  let errorMessage: string | null = null;
  try {
    data = await api.listOutreach({ status, limit: 100 });
  } catch (error) {
    errorMessage = error instanceof ApiError ? error.message : "Unexpected error.";
  }

  return (
    <>
      <PageHeader
        title="Outreach"
        description="AI-generated email and DM drafts. Nothing is sent — review, edit, approve or reject."
      />

      {errorMessage || !data ? (
        <ErrorState title="Could not load outreach" message={errorMessage ?? "No data returned."} />
      ) : (
        <Card>
          <CardHeader title="Drafts" subtitle={`${data.total} draft${data.total === 1 ? "" : "s"}`} />
          <div className="border-b border-ink-800 px-5 py-3">
            <form method="get" action="/outreach" className="flex flex-wrap items-end gap-2">
              <div className="sm:min-w-[12rem]">
                <label htmlFor="outreach-status" className="mb-1 block text-xs font-medium text-mist-300">
                  Draft status
                </label>
                <select id="outreach-status" name="status" defaultValue={status ?? ""} className="field">
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option || "all"} value={option}>
                      {option ? option.replace(/_/g, " ") : "All statuses"}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                className="min-h-11 rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-mist-200 hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
              >
                Filter
              </button>
            </form>
          </div>
          {data.items.length === 0 ? (
            <EmptyState
              title="No drafts"
              description="Drafts appear after the worker runs the ai_outreach stage."
            />
          ) : (
            <ul className="divide-y divide-ink-800">
              {data.items.map((entry) => (
                <li key={entry.lead_id} className="px-5 py-4 transition-colors hover:bg-ink-850/50">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <Link href={`/outreach/${entry.lead_id}`} className="min-w-0">
                      <span className="block font-medium text-mist-100">@{entry.username}</span>
                      <span className="mt-0.5 line-clamp-1 block text-xs text-mist-400">
                        {entry.subject || "(no subject)"}
                      </span>
                    </Link>
                    <div className="flex items-center gap-3">
                      <StatusBadge status={entry.status} />
                      <span className="w-28 text-right font-mono text-[11px] text-mist-400">
                        {formatDate(entry.generated_at)}
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
