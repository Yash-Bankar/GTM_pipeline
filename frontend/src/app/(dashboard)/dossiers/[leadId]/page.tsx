import Link from "next/link";
import { notFound } from "next/navigation";

import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  KeyValue,
  PageHeader,
  ScoreBar,
  TierBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, humanize } from "@/lib/format";
import { requireSession } from "@/lib/session";

type Params = Promise<{ leadId: string }>;

export default async function DossierDetailPage({ params }: { params: Params }) {
  await requireSession();
  const { leadId } = await params;

  let dossier;
  try {
    dossier = await api.getDossier(leadId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const criteria = Object.entries(dossier.criterion_scores ?? {});

  return (
    <>
      <PageHeader
        title={`@${dossier.username}`}
        description={`Dossier · ${humanize(dossier.status)} · ${dossier.rubric || "rubric"}`}
        actions={
          <Link
            href={`/leads/${dossier.lead_id}`}
            className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
          >
            View lead
          </Link>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader title="Summary" actions={<TierBadge tier={dossier.qualification_tier} />} />
            <p className="px-5 py-4 text-sm leading-relaxed text-mist-100">
              {dossier.summary || "No summary was produced."}
            </p>
            {dossier.topics.length > 0 ? (
              <div className="flex flex-wrap gap-2 border-t border-ink-800 px-5 py-3">
                {dossier.topics.map((topic) => (
                  <Badge key={topic} tone="teal">
                    {topic}
                  </Badge>
                ))}
              </div>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="Audience" subtitle="Only stated when supported by evidence" />
            <p className="px-5 py-4 text-sm text-mist-200">
              {dossier.audience || "Not evidenced — deliberately left blank."}
            </p>
          </Card>

          <Card>
            <CardHeader title="Uncertainty" subtitle="What the model could not verify" />
            <p className="px-5 py-4 text-sm text-mist-300">
              {dossier.uncertainty || "None recorded."}
            </p>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Qualification" />
            <div className="space-y-4 px-5 py-4">
              <ScoreBar value={dossier.qualification_score} />
              <div className="space-y-3">
                {criteria.length === 0 ? (
                  <p className="text-xs text-mist-400">No criterion scores.</p>
                ) : (
                  criteria.map(([name, score]) => (
                    <div key={name}>
                      <p className="mb-1 text-[11px] uppercase tracking-widest text-mist-400">
                        {humanize(name)}
                      </p>
                      <ScoreBar value={score} />
                    </div>
                  ))
                )}
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Sources" subtitle={`${dossier.evidence_urls.length} cited`} />
            {dossier.evidence_urls.length === 0 ? (
              <EmptyState title="No sources cited" />
            ) : (
              <ul className="space-y-1.5 px-5 py-4">
                {dossier.evidence_urls.map((url) => (
                  <li key={url} className="truncate">
                    <a href={url} target="_blank" rel="noreferrer" className="text-xs text-accent-300 hover:underline">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader title="Meta" />
            <dl className="grid grid-cols-2 gap-4 px-5 py-4">
              <KeyValue label="Model">{dossier.model || "—"}</KeyValue>
              <KeyValue label="Status">{humanize(dossier.status)}</KeyValue>
              <KeyValue label="Rubric">{dossier.rubric || "—"}</KeyValue>
              <KeyValue label="Generated">{formatDate(dossier.generated_at)}</KeyValue>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
