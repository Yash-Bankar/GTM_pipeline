"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/session";

export interface OutreachState {
  status: "idle" | "saved" | "error";
  message?: string;
}

const STATUS_LABELS: Record<string, string> = {
  APPROVED: "Draft approved.",
  REJECTED: "Draft rejected.",
  NEEDS_REVIEW: "Draft saved for review.",
};

export async function saveOutreach(
  _prev: OutreachState,
  formData: FormData,
): Promise<OutreachState> {
  await requireSession();

  const leadId = String(formData.get("leadId") ?? "");
  const status = String(formData.get("status") ?? "NEEDS_REVIEW");
  const subject = String(formData.get("subject") ?? "");
  const body = String(formData.get("body") ?? "");
  const dmBody = String(formData.get("dm_body") ?? "");

  if (!leadId) {
    return { status: "error", message: "Missing lead id." };
  }

  try {
    await api.updateOutreach(leadId, { status, subject, body, dm_body: dmBody });
    revalidatePath("/outreach");
    revalidatePath(`/outreach/${leadId}`);
    return { status: "saved", message: STATUS_LABELS[status] ?? "Saved." };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof ApiError ? error.message : "Could not save the draft.",
    };
  }
}
