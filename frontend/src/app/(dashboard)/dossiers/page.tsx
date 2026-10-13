import Link from "next/link";

import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  ScoreBar,
  TierBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { requireSession } from "@/lib/session";
import type { DossierList } from "@/lib/types";

type SearchParams = Promise<{ q?: string }>;

export default async function DossiersPage({ searchParams }: { searchParams: SearchParams }) {
  await requireSession();
  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : undefined;

  let data: DossierList | null = null;
  let errorMessage: string | null = null;
  try {
    data = await api.listDossiers({ q, limit: 100 });
  } catch (error) {
    errorMessage = error instanceof ApiError ? error.message : "Unexpected error.";
  }

  return (
    <>
      <PageHeader
        title="Dossiers"
        description="Structured AI research per creator, with qualification scoring and cited sources."
      />

      {errorMessage || !data ? (
        <ErrorState title="Could not load dossiers" message={errorMessage ?? "No data returned."} />
      ) : (
        <Card>
          <CardHeader
            title="Research"
            subtitle={`${data.total} dossier${data.total === 1 ? "" : "s"}`}
            actions={
              <form method="get" action="/dossiers" className="flex items-center gap-2">
                <input name="q" defaultValue={q ?? ""} placeholder="Search…" className="field w-48" />
                <button
                  type="submit"
                  className="rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-mist-200 hover:bg-ink-800"
                >
                  Search
                </button>
              </form>
            }
          />
          {data.items.length === 0 ? (
            <EmptyState
              title="No dossiers yet"
              description="Dossiers appear after the worker runs the ai_dossier stage (needs GEMINI_API_KEY)."
            />
          ) : (
            <ul className="divide-y divide-ink-800">
              {data.items.map((dossier) => (
                <li key={dossier.lead_id} className="px-5 py-4 transition-colors hover:bg-ink-850/50">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <Link href={`/dossiers/${dossier.lead_id}`} className="min-w-0">
                      <span className="block font-medium text-mist-100">@{dossier.username}</span>
                      <span className="mt-0.5 line-clamp-1 block text-xs text-mist-400">
                        {dossier.summary || "No summary"}
                      </span>
                    </Link>
                    <div className="flex items-center gap-4">
                      <div className="w-40">
                        <ScoreBar value={dossier.qualification_score} />
                      </div>
                      <TierBadge tier={dossier.qualification_tier} />
                      <span className="w-28 text-right font-mono text-[11px] text-mist-400">
                        {formatDate(dossier.generated_at)}
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
