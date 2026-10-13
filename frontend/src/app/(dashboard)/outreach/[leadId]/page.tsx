import Link from "next/link";
import { notFound } from "next/navigation";

import { OutreachEditor } from "@/components/outreach-editor";
import { Card, CardHeader, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";

type Params = Promise<{ leadId: string }>;

export default async function OutreachDetailPage({ params }: { params: Params }) {
  await requireSession();
  const { leadId } = await params;

  let entry;
  try {
    entry = await api.getOutreach(leadId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <>
      <PageHeader
        title={`@${entry.username}`}
        description={`Outreach draft · ${entry.model || "model"}`}
        actions={
          <Link
            href={`/leads/${entry.lead_id}`}
            className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs font-semibold text-mist-200 hover:bg-ink-800"
          >
            View lead
          </Link>
        }
      />

      <Card>
        <CardHeader title="Review draft" actions={<StatusBadge status={entry.status} />} />
        <div className="px-5 py-5">
          <OutreachEditor
            leadId={entry.lead_id}
            initial={{
              subject: entry.subject,
              body: entry.body,
              dmBody: entry.dm_body,
              status: entry.status,
            }}
          />
        </div>
      </Card>
    </>
  );
}
