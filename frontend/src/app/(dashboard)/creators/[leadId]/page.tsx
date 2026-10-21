import Link from "next/link";
import { notFound } from "next/navigation";

import { FitDecision } from "@/components/fit-decision";
import { ManualContactForm } from "@/components/manual-contact-form";
import { OutreachGates } from "@/components/outreach-gates";
import { RetryAiButton } from "@/components/retry-ai-button";
import { RetryButton } from "@/components/retry-button";
import { LiveRefresh } from "@/components/view-switcher";
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
import type { Brief, FitDecision as FitDecisionRecord, OutreachRevision } from "@/lib/types";

type Params = Promise<{ leadId: string }>;

function postsEmptyCopy(mediaStatus: string): { title: string; description: string } {
  switch ((mediaStatus || "").toLowerCase()) {
    case "error":
      return { title: "Posts unavailable", description: "Media enrichment failed for this creator." };
    case "blocked":
      return { title: "Posts blocked", description: "The media source rejected the request." };
    case "partial":
      return {
        title: "Posts partially captured",
        description: "Media enrichment returned incomplete data.",
      };
    default:
      return {
        title: "Posts not captured in snapshot",
        description:
          "Recent posts aren't part of the profile snapshot. Run media enrichment to fetch them.",
      };
  }
}

export default async function CreatorDetailPage({ params }: { params: Params }) {
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

  // The creator brief (and any AI summary) lives inside the creator detail
  // view now; the legacy /dossiers route redirects here (PRD 6.1).
  let brief: Brief | null = null;
  try {
    brief = await api.getBrief(leadId);
  } catch {
    brief = null;
  }

  const {
    lead,
    progress,
    progress_remedy: remedy,
    posts,
    website_pages: pages,
    contacts,
    contact_request: contactRequest,
    jobs,
  } = detail;
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

  // Contextual primary action (PRD 6.3).
  const hasEmail = contacts.some((contact) => contact.type === "email");
  const hasAnyContact = contacts.length > 0;
  const primaryAction = (() => {
    if (progress === "blocked") {
      return {
        label: "Read the research remedy",
        href: "#research-remedy",
        tone: "rose" as const,
        detail: remedy || "Research is blocked. See the explanation below.",
      };
    }
    if (lead.fit_status === "not_reviewed" && progress === "complete") {
      return {
        label: "Review and decide",
        href: "#fit-decision",
        tone: "accent" as const,
        detail: "Evidence is ready. Shortlist, research more or reject.",
      };
    }
    if (lead.fit_status === "not_reviewed") {
      return {
        label: "Add profile data",
        href: "#research-remedy",
        tone: "amber" as const,
        detail:
          "No useful evidence yet. Reopen the profile in the extension to capture it, or retry research.",
      };
    }
    if (lead.fit_status === "shortlisted" && lead.decision_currency === "review_needed") {
      return {
        label: "Review changes and reconfirm",
        href: "#fit-decision",
        tone: "amber" as const,
        detail: "Evidence changed since the shortlist. Reconfirm before preparing outreach.",
      };
    }
    if (lead.fit_status === "shortlisted" && hasEmail) {
      return {
        label: "Write draft",
        href: `/outreach/${lead.lead_id}`,
        tone: "accent" as const,
        detail: "A public email is available. Write a draft manually or generate one.",
      };
    }
    if (lead.fit_status === "shortlisted" && !hasAnyContact) {
      return {
        label: "Find missing contact",
        href: "#contact-and-drafts",
        tone: "amber" as const,
        detail: "No usable contact yet. Search public sources, add one, or choose Instagram DM.",
      };
    }
    return {
      label: "Prepare outreach",
      href: `/outreach/${lead.lead_id}`,
      tone: "accent" as const,
      detail: "Write a draft manually, or generate one with AI.",
    };
  })();

  const primaryToneClasses: Record<string, string> = {
    accent: "border-accent-600/60 bg-accent-500/15 text-accent-200 hover:bg-accent-500/25",
    amber:
      "border-amber-glow/40 bg-amber-glow/10 text-amber-glow hover:bg-amber-glow/20",
    rose: "border-rose-alert/40 bg-rose-alert/10 text-rose-alert hover:bg-rose-alert/20",
  };

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
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={progress} />
            <Link
              href="/creators"
              className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
            >
              Back to creators
            </Link>
            <Link
              href={`/outreach/${lead.lead_id}`}
              className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
            >
              Outreach
            </Link>
          </div>
        }
      />

      {/* Contextual primary action with its prerequisite explained beside it. */}
      <div className="mb-5 rounded-2xl border border-white/10 bg-ink-900/55 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
              Next step
            </p>
            <p className="mt-1 text-sm text-mist-200">{primaryAction.detail}</p>
          </div>
          <Link
            href={primaryAction.href}
            className={`min-h-11 inline-flex items-center rounded-lg border px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400 ${primaryToneClasses[primaryAction.tone]}`}
          >
            {primaryAction.label}
          </Link>
        </div>
      </div>

      {progress === "blocked" && remedy ? (
        <div
          id="research-remedy"
          role="alert"
          className="mb-5 flex items-start gap-3 rounded-xl border border-rose-alert/40 bg-rose-alert/10 px-4 py-3 text-sm text-rose-alert"
        >
          <span aria-hidden>⚠</span>
          <span>{remedy}</span>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          {brief ? (
            <Card>
              <CardHeader
                title="Creator brief"
                subtitle={
                  brief.evidence_version > 0
                    ? `Evidence v${brief.evidence_version} · built from captured evidence`
                    : "Built from captured evidence"
                }
                actions={
                  brief.ai_summary ? (
                    <Badge tone="blue">AI summary available</Badge>
                  ) : (
                    <Badge tone="neutral">No AI summary</Badge>
                  )
                }
              />
              {brief.ai_summary ? (
                <div className="border-b border-ink-800 px-5 py-4">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
                    AI summary
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-mist-200">
                    {brief.ai_summary}
                  </p>
                </div>
              ) : (
                <p className="border-b border-ink-800 px-5 py-3 text-xs text-mist-400">
                  No AI summary was generated. Evidence review and manual drafting still work.
                </p>
              )}
              <div className="px-5 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
                  Summary
                </p>
                <p className="mt-1 text-sm leading-relaxed text-mist-200">
                  {brief.full_name || brief.category || "Creator profile"}{" "}
                  {brief.follower_display
                    ? `· ${brief.follower_precision === "approximate" ? "~" : ""}${brief.follower_display} followers`
                    : ""}
                </p>
                {brief.observed_topics.length > 0 ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
                      Observed topics
                    </span>
                    {brief.observed_topics.map((topic) => (
                      <Badge key={topic} tone="teal">
                        {topic}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            </Card>
          ) : null}

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
              <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
                Links
              </p>
              {links.length > 0 ? (
                <ul className="mt-1 space-y-1">
                  {links.map((url) => (
                    <li key={url}>
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400break-all text-sm text-accent-300 hover:underline"
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
                      <p className="line-clamp-2 text-sm text-mist-200">
                        {post.caption || "(no caption)"}
                      </p>
                      <a
                        href={post.url}
                        target="_blank"
                        rel="noreferrer"
                        className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400shrink-0 text-xs text-accent-300 hover:underline"
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
              <EmptyState
                title="No website pages"
                description="No external link, or crawl blocked/failed."
              />
            ) : (
              <ul className="divide-y divide-ink-800">
                {pages.map((page) => (
                  <li key={page.page_id} className="px-5 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <a
                        href={page.resolved_url || page.url}
                        target="_blank"
                        rel="noreferrer"
                        className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400truncate text-sm text-mist-100 hover:text-accent-200"
                      >
                        {page.title || page.url}
                      </a>
                      <Badge
                        tone={
                          page.status === "done"
                            ? "green"
                            : page.status === "blocked"
                              ? "red"
                              : "amber"
                        }
                      >
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

          <Card>
            <CardHeader title="Public contacts" subtitle={`${contacts.length} found`} />
            {contacts.length === 0 ? (
              <EmptyState
                title="No public contacts found"
                description="No email or phone was found in the captured bio or crawled pages."
              />
            ) : (
              <ul className="divide-y divide-ink-800">
                {contacts.map((contact) => (
                  <li key={contact.contact_id} className="px-5 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="break-all font-mono text-sm text-mist-100">
                        {contact.value}
                      </span>
                      <Badge tone={contact.type === "email" ? "teal" : "neutral"}>
                        {humanize(contact.type)}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-mist-400">
                      {contact.provenance}
                      {contact.source_url ? (
                        <>
                          {" · "}
                          <a
                            href={contact.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400text-accent-300 hover:underline"
                          >
                            {contact.source_url}
                          </a>
                        </>
                      ) : null}
                      {" · "}
                      {formatDate(contact.observed_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            <ManualContactForm leadId={lead.lead_id} />
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
            <div id="fit-decision">
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
            </div>
          </Card>

          <Card>
            <div id="contact-and-drafts">
              <CardHeader title="Contact & drafts" subtitle="Requires a current shortlist" />
              <OutreachGates
                leadId={lead.lead_id}
                enabled={outreachEnabled}
                reason={gateReason}
                contactRequest={contactRequest}
              />
            </div>
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
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-mist-400">Research</span>
                <StatusBadge status={progress} />
              </div>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-mist-400">Media</span>
                <StatusBadge status={lead.media_status || "none"} />
              </div>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-mist-400">Website</span>
                <StatusBadge status={lead.website_status || "none"} />
              </div>
              <div className="space-y-2 border-t border-ink-800 pt-3">
                <RetryButton leadId={lead.lead_id} />
                <RetryAiButton leadId={lead.lead_id} />
              </div>
            </div>
          </Card>

          <details className="rounded-2xl border border-white/10 bg-ink-900/55 px-5 py-4">
            <summary className="cursor-pointer text-sm font-semibold text-mist-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400">
              Activity · {jobs.length} job{jobs.length === 1 ? "" : "s"}
            </summary>
            <div className="mt-2">
              <LiveRefresh
                pending={jobs.some(
                  (job) => job.status === "queued" || job.status === "running" || job.status === "retry",
                )}
              />
            </div>
            {jobs.length === 0 ? (
              <EmptyState title="No jobs" />
            ) : (
              <ul className="mt-3 divide-y divide-ink-800">
                {jobs.map((job) => (
                  <li key={job.job_id} className="py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs text-mist-200">{job.stage}</span>
                      <StatusBadge status={job.status} />
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-mist-400">
                      attempt {job.attempt_count}/{job.max_attempts} ·{" "}
                      {job.updated_at.slice(0, 16).replace("T", " ")}
                    </p>
                    {job.last_error ? (
                      <p className="mt-1 text-xs text-rose-alert">{job.last_error}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </details>
        </div>
      </div>
    </>
  );
}
