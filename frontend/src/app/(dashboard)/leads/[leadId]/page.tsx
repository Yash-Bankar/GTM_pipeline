import Link from "next/link";
import { notFound } from "next/navigation";

import { FitDecision } from "@/components/fit-decision";
import { OutreachGates } from "@/components/outreach-gates";
import { RetryAiButton } from "@/components/retry-ai-button";
import { RetryButton } from "@/components/retry-button";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  KeyValue,
  PageHeader,
  StatusBadge,
  VerifiedBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import {
  formatCount,
  followerLabel,
  formatDate,
  formatNumber,
  humanize,
  splitUrls,
} from "@/lib/format";
import { requireSession } from "@/lib/session";
import type { FitDecision as FitDecisionRecord, OutreachRevision } from "@/lib/types";

type Params = Promise<{ leadId: string }>;

function postsEmptyCopy(mediaStatus: string): { title: string; description: string } {
  switch ((mediaStatus || "").toLowerCase()) {
    case "error":
      return { title: "Posts unavailable", description: "Media enrichment failed for this creator." };
    case "blocked":
      return { title: "Posts blocked", description: "The media source rejected the request." };
    case "partial":
      return { title: "Posts partially captured", description: "Media enrichment returned incomplete data." };
    default:
      return {
        title: "Posts not captured in snapshot",
        description: "Recent posts aren't part of the profile snapshot. Run media enrichment to fetch them.",
      };
  }
}

export default async function LeadDetailPage({ params }: { params: Params }) {
  await requireSession();
  const { leadId } = await params;

  let detail;
  try {
    detail = await api.leadDetail(leadId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  let revisions: OutreachRevision[] = [];
  try {
    revisions = (await api.listDraftRevisions(leadId)).items;
  } catch {
    revisions = [];
  }

  let decisions: FitDecisionRecord[] = [];
  try {
    decisions = (await api.listFitDecisions(leadId)).items;
  } catch {
    decisions = [];
  }

  const { lead, progress, progress_remedy: remedy, posts, website_pages: pages, jobs } = detail;
  const snapshot = lead.snapshot;
  const links = splitUrls(lead.all_external_urls);
  const postsEmpty = postsEmptyCopy(lead.media_status);
  const outreachEnabled =
    lead.fit_status === "shortlisted" && lead.decision_currency === "current";
  const gateReason =
    lead.fit_status !== "shortlisted"
      ? "Shortlist this creator with current evidence before requesting contact details or drafts."
      : lead.decision_currency !== "current"
        ? "Review needed: evidence changed since the shortlist. Reconfirm fit before preparing outreach."
        : "";

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            @{lead.username}
            {snapshot?.is_verified ? <VerifiedBadge /> : null}
          </span>
        }
        description={lead.full_name || lead.business_category_name || "Creator profile"}
        actions={
          <div className="flex items-center gap-3">
            <StatusBadge status={progress} />
            <Link
              href={`/dossiers/${lead.lead_id}`}
              className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
            >
              Dossier
            </Link>
            <Link
              href={`/outreach/${lead.lead_id}`}
              className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
            >
              Outreach
            </Link>
          </div>
        }
      />

      {progress === "blocked" && remedy ? (
        <div
          role="alert"
          className="mb-5 flex items-start gap-3 rounded-xl border border-rose-alert/40 bg-rose-alert/10 px-4 py-3 text-sm text-rose-alert"
        >
          <span aria-hidden>⚠</span>
          <span>{remedy}</span>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Profile"
              subtitle={snapshot?.source_url || lead.profile_url}
              actions={<StatusBadge status={progress} />}
            />
            <dl className="grid grid-cols-2 gap-4 px-5 py-4 sm:grid-cols-3">
              <KeyValue label="Followers">{followerLabel(lead)}</KeyValue>
              <KeyValue label="Following">
                {snapshot?.following ? formatCount(snapshot.following) : formatNumber(lead.follows_count)}
              </KeyValue>
              <KeyValue label="Posts">
                {snapshot?.post_count ? formatCount(snapshot.post_count) : "Unknown"}
              </KeyValue>
              <KeyValue label="Category">{lead.business_category_name || "—"}</KeyValue>
              <KeyValue label="Email">{lead.business_email || "—"}</KeyValue>
              <KeyValue label="Phone">{lead.business_phone_number || "—"}</KeyValue>
            </dl>
            {snapshot && snapshot.missing_fields.length > 0 ? (
              <p className="border-t border-ink-800 px-5 py-3 text-xs text-amber-glow">
                Missing: {snapshot.missing_fields.join(", ")}
              </p>
            ) : null}
            <div className="border-t border-ink-800 px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">Bio</p>
              <p className="mt-1 text-sm leading-relaxed text-mist-200">
                {lead.bio || "No bio captured."}
              </p>
            </div>
            <div className="border-t border-ink-800 px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">Links</p>
              {links.length > 0 ? (
                <ul className="mt-1 space-y-1">
                  {links.map((url) => (
                    <li key={url}>
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="break-all text-sm text-accent-300 hover:underline"
                      >
                        {url}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-mist-400">No external links captured.</p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Recent posts"
              subtitle={posts.length > 0 ? `${posts.length} stored` : postsEmpty.title}
            />
            {posts.length === 0 ? (
              <EmptyState title={postsEmpty.title} description={postsEmpty.description} />
            ) : (
              <ul className="divide-y divide-ink-800">
                {posts.map((post) => (
                  <li key={post.post_id} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="line-clamp-2 text-sm text-mist-200">{post.caption || "(no caption)"}</p>
                      <a
                        href={post.url}
                        target="_blank"
                        rel="noreferrer"
                        className="shrink-0 text-xs text-accent-300 hover:underline"
                      >
                        open
                      </a>
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-mist-400">
                      {post.product_type || post.media_type} · ♥ {formatNumber(post.like_count)} · 💬{" "}
                      {formatNumber(post.comment_count)} · ▶ {formatNumber(post.play_count)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader title="Website pages" subtitle={`${pages.length} crawled`} />
            {pages.length === 0 ? (
              <EmptyState title="No website pages" description="No external link, or crawl blocked/failed." />
            ) : (
              <ul className="divide-y divide-ink-800">
                {pages.map((page) => (
                  <li key={page.page_id} className="px-5 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <a
                        href={page.resolved_url || page.url}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate text-sm text-mist-100 hover:text-accent-200"
                      >
                        {page.title || page.url}
                      </a>
                      <Badge tone={page.status === "done" ? "green" : page.status === "blocked" ? "red" : "amber"}>
                        {humanize(page.status)}
                      </Badge>
                    </div>
                    {page.error ? (
                      <p className="mt-1 text-xs text-rose-alert">{page.error}</p>
                    ) : (
                      <p className="mt-1 line-clamp-2 text-xs text-mist-400">{page.text}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {revisions.length > 0 ? (
            <Card>
              <CardHeader
                title="Draft revision history"
                subtitle={`${revisions.length} request${revisions.length === 1 ? "" : "s"}`}
              />
              <ul className="divide-y divide-ink-800">
                {revisions.map((revision) => (
                  <li
                    key={revision.revision_id}
                    className="flex flex-wrap items-center justify-between gap-2 px-5 py-3"
                  >
                    <div>
                      <p className="text-sm text-mist-100">{humanize(revision.channel)}</p>
                      <p className="font-mono text-[11px] text-mist-400">
                        {formatDate(revision.requested_at || revision.created_at)}
                      </p>
                    </div>
                    <Badge tone={revision.status === "requested" ? "blue" : "neutral"}>
                      {humanize(revision.status)}
                    </Badge>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Fit decision" subtitle="Separate from research progress" />
            <FitDecision
              leadId={lead.lead_id}
              fitStatus={lead.fit_status}
              fitNote={lead.fit_note}
              fitDecidedAt={lead.fit_decided_at}
              decisionCurrency={lead.decision_currency}
              currencyReason={lead.decision_currency_reason}
              newEvidenceAvailable={lead.new_evidence_available}
            />
          </Card>

          <Card>
            <CardHeader
              title="Contact & drafts"
              subtitle="Requires a current shortlist"
            />
            <OutreachGates
              leadId={lead.lead_id}
              enabled={outreachEnabled}
              reason={gateReason}
            />
          </Card>

          {decisions.length > 0 ? (
            <Card>
              <CardHeader
                title="Decision history"
                subtitle={`${decisions.length} event${decisions.length === 1 ? "" : "s"}`}
              />
              <ul className="divide-y divide-ink-800">
                {decisions.map((decision) => (
                  <li key={decision.decision_id} className="px-5 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm text-mist-100">{humanize(decision.action)}</span>
                      <Badge
                        tone={decision.decision_currency === "review_needed" ? "amber" : "neutral"}
                      >
                        {humanize(decision.decision_currency)}
                      </Badge>
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-mist-400">
                      {humanize(decision.fit_status)} · evidence v{decision.evidence_version} ·
                      criteria v{decision.criteria_version} · {formatDate(decision.created_at)} ·{" "}
                      {decision.actor}
                    </p>
                    {decision.note ? (
                      <p className="mt-1 text-xs text-mist-300">{decision.note}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Processing" subtitle="Re-run stages manually" />
            <div className="space-y-3 px-5 py-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-mist-400">Research</span>
                <StatusBadge status={progress} />
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-mist-400">Media</span>
                <StatusBadge status={lead.media_status || "none"} />
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-mist-400">Website</span>
                <StatusBadge status={lead.website_status || "none"} />
              </div>
              <div className="space-y-2 border-t border-ink-800 pt-3">
                <RetryButton leadId={lead.lead_id} />
                <RetryAiButton leadId={lead.lead_id} />
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Job history" subtitle={`${jobs.length} jobs`} />
            {jobs.length === 0 ? (
              <EmptyState title="No jobs" />
            ) : (
              <ul className="divide-y divide-ink-800">
                {jobs.map((job) => (
                  <li key={job.job_id} className="px-5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs text-mist-200">{job.stage}</span>
                      <StatusBadge status={job.status} />
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-mist-400">
                      attempt {job.attempt_count}/{job.max_attempts} · {job.updated_at.slice(0, 16).replace("T", " ")}
                    </p>
                    {job.last_error ? (
                      <p className="mt-1 text-xs text-rose-alert">{job.last_error}</p>
                    ) : null}
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
