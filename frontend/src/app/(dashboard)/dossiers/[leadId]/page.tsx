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
  VerifiedBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, formatNumber, humanize } from "@/lib/format";
import { requireSession } from "@/lib/session";
import type { Brief, Dossier } from "@/lib/types";

type Params = Promise<{ leadId: string }>;

function followerText(brief: Brief): string {
  if (!brief.follower_display) {
    return brief.follower_count > 0 ? formatNumber(brief.follower_count) : "Unknown";
  }
  return brief.follower_precision === "approximate"
    ? `~${brief.follower_display}`
    : brief.follower_display;
}

function BriefView({ brief }: { brief: Brief }) {
  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            @{brief.username}
            {brief.is_verified ? <VerifiedBadge /> : null}
          </span>
        }
        description={`Creator brief${
          brief.evidence_version > 0 ? ` · Evidence v${brief.evidence_version}` : ""
        } · AI summary not generated`}
        actions={
          <Link
            href={`/leads/${brief.lead_id}`}
            className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
          >
            View lead
          </Link>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Profile"
              subtitle={
                brief.captured_at
                  ? `Captured ${formatDate(brief.captured_at)}`
                  : "Captured profile evidence"
              }
            />
            <dl className="grid grid-cols-2 gap-4 px-5 py-4 sm:grid-cols-3">
              <KeyValue label="Followers">{followerText(brief)}</KeyValue>
              <KeyValue label="Following">{formatNumber(brief.follows_count)}</KeyValue>
              <KeyValue label="Category">{brief.category || "—"}</KeyValue>
            </dl>
            <div className="border-t border-ink-800 px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
                Bio
              </p>
              <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-mist-200">
                {brief.bio || "No bio captured."}
              </p>
            </div>
            {brief.missing_fields.length > 0 ? (
              <p className="border-t border-ink-800 px-5 py-3 text-xs text-amber-glow">
                Missing: {brief.missing_fields.join(", ")}
              </p>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="Website sources" subtitle={`${brief.sources.length} observed`} />
            {brief.sources.length === 0 ? (
              <EmptyState title="No website sources observed" />
            ) : (
              <ul className="divide-y divide-ink-800">
                {brief.sources.map((source) => (
                  <li
                    key={source.url}
                    className="flex items-center justify-between gap-3 px-5 py-3"
                  >
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate text-sm text-mist-100 hover:text-accent-200"
                    >
                      {source.title || source.url}
                    </a>
                    <Badge
                      tone={
                        source.status === "done"
                          ? "green"
                          : source.status === "blocked"
                            ? "red"
                            : "amber"
                      }
                    >
                      {humanize(source.status)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="AI summary" subtitle="Optional" />
            <div className="px-5 py-4 text-sm text-mist-300">
              <p>Not generated. This brief is built entirely from captured evidence.</p>
              <p className="mt-2 text-xs text-mist-400">
                Running an AI summary is an explicit action and is not required to review this
                creator.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader title="Links" />
            {brief.external_urls.length === 0 ? (
              <EmptyState title="No links captured" />
            ) : (
              <ul className="space-y-1.5 px-5 py-4">
                {brief.external_urls.map((url) => (
                  <li key={url}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="break-all text-xs text-accent-300 hover:underline"
                    >
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

export default async function DossierDetailPage({ params }: { params: Params }) {
  await requireSession();
  const { leadId } = await params;

  let dossier: Dossier | null = null;
  let brief: Brief | null = null;
  try {
    dossier = await api.getDossier(leadId);
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) throw error;
    // V2-01: with AI disabled there is no dossier row; render the evidence brief.
    try {
      brief = await api.getBrief(leadId);
    } catch (briefError) {
      if (briefError instanceof ApiError && briefError.status === 404) notFound();
      throw briefError;
    }
  }

  if (dossier === null) {
    if (brief === null) notFound();
    return <BriefView brief={brief} />;
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
