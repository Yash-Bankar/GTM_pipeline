import Link from "next/link";
import { notFound } from "next/navigation";

import { RetryButton } from "@/components/retry-button";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  KeyValue,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatNumber, humanize } from "@/lib/format";
import { requireSession } from "@/lib/session";

type Params = Promise<{ leadId: string }>;

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

  const { lead, posts, website_pages: pages, jobs } = detail;

  return (
    <>
      <PageHeader
        title={`@${lead.username}`}
        description={lead.full_name || lead.business_category_name || "Creator profile"}
        actions={
          <div className="flex items-center gap-3">
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

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Profile"
              subtitle={lead.profile_url}
              actions={<StatusBadge status={lead.status} />}
            />
            <dl className="grid grid-cols-2 gap-4 px-5 py-4 sm:grid-cols-3">
              <KeyValue label="Followers">{formatNumber(lead.follower_count)}</KeyValue>
              <KeyValue label="Following">{formatNumber(lead.follows_count)}</KeyValue>
              <KeyValue label="Category">{lead.business_category_name || "—"}</KeyValue>
              <KeyValue label="Email">{lead.business_email || "—"}</KeyValue>
              <KeyValue label="Phone">{lead.business_phone_number || "—"}</KeyValue>
              <KeyValue label="Engagement">{lead.engagement_rate || "—"}</KeyValue>
            </dl>
            {lead.bio ? (
              <p className="border-t border-ink-800 px-5 py-4 text-sm leading-relaxed text-mist-200">
                {lead.bio}
              </p>
            ) : null}
            {lead.external_url ? (
              <p className="border-t border-ink-800 px-5 py-3 text-xs text-mist-400">
                Website:{" "}
                <a href={lead.external_url} target="_blank" rel="noreferrer" className="text-accent-300 hover:underline">
                  {lead.external_url}
                </a>
              </p>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="Recent posts" subtitle={`${posts.length} stored`} />
            {posts.length === 0 ? (
              <EmptyState title="No posts collected" description="Media may still be processing." />
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
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Processing" />
            <div className="space-y-3 px-5 py-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-mist-400">Media</span>
                <StatusBadge status={lead.media_status || "none"} />
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-mist-400">Website</span>
                <StatusBadge status={lead.website_status || "none"} />
              </div>
              <RetryButton leadId={lead.lead_id} />
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
