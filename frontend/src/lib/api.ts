/**
 * Server-side API client for the Python backend.
 *
 * Server-only by convention: never import this from a Client Component. Secrets
 * (BACKEND_API_KEY, API_BASE_URL) stay on the server and are never sent to the
 * browser.
 */

import { ApiError } from "./errors";
import type {
  Dossier,
  DossierList,
  LeadDetail,
  LeadList,
  LeadSubmission,
  Outreach,
  OutreachList,
  RetryAiResult,
  Stats,
} from "./types";

const BASE_URL = (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const API_KEY = (process.env.BACKEND_API_KEY ?? "").trim();

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("accept", "application/json");
  if (init?.body !== undefined) headers.set("content-type", "application/json");
  if (API_KEY) headers.set("x-api-key", API_KEY);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Could not reach the backend API. Is it running?");
  }

  if (!response.ok) {
    let detail = response.statusText || `Request failed (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data?.detail === "string") {
        detail = data.detail;
      } else if (data?.detail && typeof data.detail === "object") {
        const structured = data.detail as { message?: unknown };
        detail =
          typeof structured.message === "string"
            ? structured.message
            : JSON.stringify(data.detail);
      }
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  listLeads(params: { limit?: number; offset?: number; q?: string; status?: string } = {}) {
    return request<LeadList>(`/api/v1/leads${buildQuery(params)}`);
  },

  createLead(body: { username: string; source?: string }) {
    return request<LeadSubmission>("/api/v1/leads", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  leadDetail(leadId: string) {
    return request<LeadDetail>(`/api/v1/leads/${encodeURIComponent(leadId)}/detail`);
  },

  retryLead(leadId: string) {
    return request<unknown>(`/api/v1/leads/${encodeURIComponent(leadId)}/retry`, {
      method: "POST",
    });
  },

  retryAi(leadId: string) {
    return request<RetryAiResult>(`/api/v1/leads/${encodeURIComponent(leadId)}/retry-ai`, {
      method: "POST",
    });
  },

  listDossiers(params: { limit?: number; offset?: number; q?: string } = {}) {
    return request<DossierList>(`/api/v1/dossiers${buildQuery(params)}`);
  },

  getDossier(leadId: string) {
    return request<Dossier>(`/api/v1/dossiers/${encodeURIComponent(leadId)}`);
  },

  listOutreach(params: { limit?: number; offset?: number; status?: string } = {}) {
    return request<OutreachList>(`/api/v1/outreach${buildQuery(params)}`);
  },

  getOutreach(leadId: string) {
    return request<Outreach>(`/api/v1/outreach/${encodeURIComponent(leadId)}`);
  },

  updateOutreach(
    leadId: string,
    body: { status?: string; subject?: string; body?: string; dm_body?: string },
  ) {
    return request<Outreach>(`/api/v1/outreach/${encodeURIComponent(leadId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  stats() {
    return request<Stats>("/api/v1/stats");
  },
};
