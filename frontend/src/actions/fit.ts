"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";

export type FitAction = "approve" | "reject" | "need_evidence";

export interface ActionResult {
  ok: boolean;
  message: string;
}

const FIT_MESSAGES: Record<FitAction, string> = {
  approve: "Fit approved. Contact and draft requests are now enabled.",
  reject: "Fit rejected.",
  need_evidence: "Marked as needing more evidence.",
};

export async function decideFit(input: {
  leadId: string;
  action: FitAction;
  note?: string;
}): Promise<ActionResult> {
  await requireSession();
  if (!input.leadId) return { ok: false, message: "Missing lead id." };

  const note = (input.note ?? "").trim();
  if (input.action === "reject" && !note) {
    return { ok: false, message: "A rejection note is required." };
  }

  try {
    await api.decideFit(input.leadId, { action: input.action, note });
    revalidatePath(`/leads/${input.leadId}`);
    revalidatePath("/leads");
    return { ok: true, message: FIT_MESSAGES[input.action] };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError ? error.message : "Could not save the fit decision.",
    };
  }
}

export async function requestContact(leadId: string): Promise<ActionResult> {
  await requireSession();
  if (!leadId) return { ok: false, message: "Missing lead id." };
  try {
    await api.requestContact(leadId);
    revalidatePath(`/leads/${leadId}`);
    return { ok: true, message: "Contact request queued." };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError ? error.message : "Could not request contact details.",
    };
  }
}

export async function requestDraft(
  leadId: string,
  channel: "email" | "instagram_dm",
): Promise<ActionResult> {
  await requireSession();
  if (!leadId) return { ok: false, message: "Missing lead id." };
  try {
    await api.requestDraft(leadId, channel);
    revalidatePath(`/leads/${leadId}`);
    return { ok: true, message: "Draft request created (a new revision was recorded)." };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError ? error.message : "Could not request a draft.",
    };
  }
}
