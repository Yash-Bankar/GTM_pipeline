"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";

export type FitAction = "shortlist" | "research_more" | "reject" | "reopen";

export interface ActionResult {
  ok: boolean;
  message: string;
}

const FIT_MESSAGES: Record<FitAction, string> = {
  shortlist: "Creator shortlisted. Contact and draft requests are now enabled.",
  research_more: "Marked as needing more research.",
  reject: "Creator rejected.",
  reopen: "Creator reopened to Not reviewed.",
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
    revalidatePath(`/creators/${input.leadId}`);
    revalidatePath("/creators");
    return { ok: true, message: FIT_MESSAGES[input.action] };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError ? error.message : "Could not save the fit decision.",
    };
  }
}

export async function requestContact(
  leadId: string,
  searchAgain = false,
): Promise<ActionResult> {
  await requireSession();
  if (!leadId) return { ok: false, message: "Missing lead id." };
  try {
    const request = await api.requestContact(leadId, "", searchAgain);
    revalidatePath(`/creators/${leadId}`);
    if (request.status === "found") {
      return { ok: true, message: "Public contact found. Review it below." };
    }
    if (request.status === "not_found") {
      return { ok: true, message: "No public contact found in searched sources." };
    }
    return { ok: true, message: "Contact search queued." };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError ? error.message : "Could not request contact details.",
    };
  }
}

export async function addContact(
  leadId: string,
  input: { type: "email" | "phone"; value: string; sourceUrl: string },
): Promise<ActionResult> {
  await requireSession();
  if (!leadId) return { ok: false, message: "Missing lead id." };
  if (!input.value.trim() || !input.sourceUrl.trim()) {
    return { ok: false, message: "Contact value and source URL are required." };
  }
  try {
    await api.addContact(leadId, {
      type: input.type,
      value: input.value.trim(),
      source_url: input.sourceUrl.trim(),
    });
    revalidatePath(`/creators/${leadId}`);
    return { ok: true, message: "Contact added with source." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof ApiError ? error.message : "Could not add the contact.",
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
    revalidatePath(`/creators/${leadId}`);
    return { ok: true, message: "Draft request created (a new revision was recorded)." };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError ? error.message : "Could not request a draft.",
    };
  }
}
