"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";

export interface AddLeadState {
  status: "idle" | "created" | "duplicate" | "error";
  message?: string;
  leadId?: string;
}

export async function addLead(_prev: AddLeadState, formData: FormData): Promise<AddLeadState> {
  await requireSession();

  const username = String(formData.get("username") ?? "").trim();
  if (!username) {
    return { status: "error", message: "Enter a username or Instagram profile URL." };
  }

  try {
    const result = await api.createLead({ username, source: "dashboard" });
    revalidatePath("/leads");
    return {
      status: result.created ? "created" : "duplicate",
      leadId: result.lead.lead_id,
      message: result.created
        ? `Queued @${result.lead.username} for processing.`
        : `@${result.lead.username} is already in the pipeline.`,
    };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof ApiError ? error.message : "Could not add the lead.",
    };
  }
}

export interface RetryState {
  ok: boolean;
  message: string;
}

export async function retryLead(leadId: string): Promise<RetryState> {
  await requireSession();
  try {
    await api.retryLead(leadId);
    revalidatePath(`/leads/${leadId}`);
    revalidatePath("/leads");
    return { ok: true, message: "Re-queued for processing." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof ApiError ? error.message : "Retry failed.",
    };
  }
}

export async function retryAi(leadId: string): Promise<RetryState> {
  await requireSession();
  try {
    const result = await api.retryAi(leadId);
    revalidatePath(`/leads/${leadId}`);
    revalidatePath("/leads");
    const count = result.jobs?.length ?? 0;
    return { ok: true, message: `Re-queued ${count} AI job${count === 1 ? "" : "s"}.` };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof ApiError ? error.message : "Could not re-queue AI jobs.",
    };
  }
}
