"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";

export interface DraftActionState {
  status: "idle" | "saved" | "error";
  message?: string;
}

export interface OutreachLogState {
  status: "idle" | "saved" | "error";
  message?: string;
}

export type OutreachOutcome =
  | "sent"
  | "replied"
  | "interested"
  | "not_interested"
  | "follow_up";

const OUTCOME_LABELS: Record<OutreachOutcome, string> = {
  sent: "Sent",
  replied: "Replied",
  interested: "Interested",
  not_interested: "Not interested",
  follow_up: "Follow up",
};

function messageFor(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/**
 * Save the draft as a NEW revision. Manual writing never needs an AI key.
 * The previous version is kept as visible history.
 */
export async function saveDraftVersion(
  _prev: DraftActionState,
  formData: FormData,
): Promise<DraftActionState> {
  await requireSession();

  const leadId = String(formData.get("leadId") ?? "");
  const revisionId = String(formData.get("revisionId") ?? "");
  if (!leadId) return { status: "error", message: "Missing lead id." };

  const subject = String(formData.get("subject") ?? "");
  const body = String(formData.get("body") ?? "");
  const dmBody = String(formData.get("dm_body") ?? "");
  if (!subject.trim() && !body.trim() && !dmBody.trim()) {
    return { status: "error", message: "A draft needs a subject, body or DM text." };
  }

  try {
    await api.saveDraft(leadId, {
      subject,
      body,
      dm_body: dmBody,
      parent_revision_id: revisionId,
    });
    revalidatePath(`/outreach/${leadId}`);
    revalidatePath("/outreach");
    return { status: "saved", message: "Draft saved as a new version." };
  } catch (error) {
    return { status: "error", message: messageFor(error, "Could not save the draft.") };
  }
}

/** Mark the current version as reviewed. */
export async function markDraftReviewed(
  leadId: string,
  revisionId: string,
): Promise<DraftActionState> {
  await requireSession();
  if (!leadId || !revisionId) {
    return { status: "error", message: "Missing draft version." };
  }
  try {
    await api.markDraftReviewed(leadId, revisionId);
    revalidatePath(`/outreach/${leadId}`);
    revalidatePath("/outreach");
    return { status: "saved", message: "Marked reviewed." };
  } catch (error) {
    return {
      status: "error",
      message: messageFor(error, "Could not mark the draft reviewed."),
    };
  }
}

/**
 * Request a new AI-generated version. The request creates a new revision when
 * it succeeds; earlier versions are never replaced.
 */
export async function generateDraftVersion(
  leadId: string,
  revisionId: string,
  channel: "email" | "instagram_dm" = "email",
): Promise<DraftActionState> {
  await requireSession();
  if (!leadId) return { status: "error", message: "Missing lead id." };
  try {
    await api.generateDraft(leadId, {
      channel,
      parent_revision_id: revisionId,
    });
    revalidatePath(`/outreach/${leadId}`);
    return {
      status: "saved",
      message: "Generation requested. A new version appears when it completes.",
    };
  } catch (error) {
    return {
      status: "error",
      message: messageFor(error, "Could not request a new version."),
    };
  }
}

/**
 * Log an outreach event manually. Only an explicit log creates a Sent event;
 * copying or exporting a draft never does.
 */
export async function logOutreachEvent(
  _prev: OutreachLogState,
  formData: FormData,
): Promise<OutreachLogState> {
  await requireSession();

  const leadId = String(formData.get("leadId") ?? "");
  const outcome = String(formData.get("outcome") ?? "") as OutreachOutcome;
  const channel = String(formData.get("channel") ?? "") as "email" | "instagram_dm";
  const sentAt = String(formData.get("sent_at") ?? "");
  const revisionId = String(formData.get("revisionId") ?? "");
  const note = String(formData.get("note") ?? "");
  const correctsEventId = String(formData.get("corrects_event_id") ?? "");

  if (!leadId) return { status: "error", message: "Missing lead id." };
  if (!outcome || !(outcome in OUTCOME_LABELS)) {
    return { status: "error", message: "Choose what happened." };
  }
  if (!channel) return { status: "error", message: "Choose a channel." };
  if (!sentAt.trim()) {
    return { status: "error", message: "Enter when it was sent." };
  }
  if (!revisionId.trim() && !note.trim()) {
    return {
      status: "error",
      message: "Add the draft version or a note describing what was sent.",
    };
  }

  try {
    await api.logOutreachEvent(leadId, {
      outcome,
      channel,
      sent_at: sentAt.trim(),
      revision_id: revisionId.trim(),
      note: note.trim(),
      corrects_event_id: correctsEventId.trim(),
    });
    revalidatePath(`/outreach/${leadId}`);
    return {
      status: "saved",
      message: correctsEventId.trim()
        ? "Correction logged. The earlier entry stays in the history."
        : `${OUTCOME_LABELS[outcome]} logged manually.`,
    };
  } catch (error) {
    return {
      status: "error",
      message: messageFor(error, "Could not log the event."),
    };
  }
}
