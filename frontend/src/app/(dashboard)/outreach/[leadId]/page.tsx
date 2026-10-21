import Link from "next/link";
import { notFound } from "next/navigation";

import { DraftEditor } from "@/components/draft-editor";
import { OutreachHistory } from "@/components/outreach-history";
import { Card, CardHeader, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { requireSession } from "@/lib/session";

type Params = Promise<{ leadId: string }>;

export default async function OutreachDetailPage({ params }: { params: Params }) {
  await requireSession();
  const { leadId } = await params;

  let entry;
  let drafts;
  let events;
  let aiAvailable = false;
  try {
    const [draftsResult, eventsResult, integrations] = await Promise.all([
      api.listDrafts(leadId),
      api.listOutreachEvents(leadId),
      api.integrationsStatus(),
    ]);
    entry = await api.getOutreach(leadId);
    drafts = draftsResult;
    events = eventsResult;
    aiAvailable = integrations.gemini === "configured";
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const current =
    drafts.items.filter((draft) => draft.status !== "superseded").slice(-1)[0] ??
    drafts.items.slice(-1)[0] ??
    null;

  const older = drafts.items.filter((draft) => draft.revision_id !== current?.revision_id);

  return (
    <>
      <PageHeader
        title={`@${entry.username}`}
        description={`Outreach draft · ${current?.model || entry.model || "manual"}`}
        actions={
          <Link
            href={`/creators/${entry.lead_id}`}
            className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
          >
            View lead
          </Link>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader
            title={current ? "Review draft" : "Write draft"}
            actions={
              current ? <StatusBadge status={current.status} /> : undefined
            }
          />
          <div className="px-5 py-5">
            <DraftEditor
              leadId={leadId}
              revisionId={current?.revision_id ?? ""}
              subject={current?.subject ?? entry.subject}
              body={current?.body ?? entry.body}
              dmBody={current?.dm_body ?? entry.dm_body}
              status={current?.status ?? "needs_review"}
              method={current?.method ?? "manual"}
              canGenerate={aiAvailable}
            />
          </div>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Log sent" />
            <div className="px-5 py-5">
              <OutreachHistory
                leadId={leadId}
                revisionId={current?.revision_id ?? ""}
                events={events.items}
              />
            </div>
          </Card>

          {older.length > 0 ? (
            <Card>
              <CardHeader title="Earlier versions" subtitle={`${older.length} kept`} />
              <ul className="divide-y divide-ink-800">
                {older.map((draft) => (
                  <li key={draft.revision_id} className="px-5 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm text-mist-200">
                        {draft.subject || "(no subject)"}
                      </span>
                      <StatusBadge status={draft.status} />
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-mist-500">
                      {draft.method} · {formatDate(draft.edited_at || draft.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}
