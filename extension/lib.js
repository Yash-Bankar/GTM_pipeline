/**
 * Shared, dependency-free helpers for the Synpo GTM extension.
 *
 * Loaded as a classic script (content/background/popup) via the global
 * `SynpoLib`, and as a CommonJS module in Node tests (`lib.test.js`).
 *
 * Contains no provider secrets and performs no scraping: it only turns the
 * current Instagram URL into a handle and calls the backend API.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.SynpoLib = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const BLOCKED_SEGMENTS = new Set([
    "",
    "accounts",
    "about",
    "api",
    "developer",
    "direct",
    "explore",
    "legal",
    "p",
    "privacy",
    "reel",
    "reels",
    "stories",
    "terms",
    "tv",
  ]);

  const DEFAULT_API_BASE = "http://127.0.0.1:8000";

  /** Extract a profile handle from an Instagram URL, path, or raw handle. */
  function extractHandle(input) {
    let value = (input || "").trim();
    if (!value) return "";

    if (value.includes("instagram.com/")) {
      value = value.split("instagram.com/", 1)[1] || value.split("instagram.com/")[1] || "";
      value = value.split(/[?#]/)[0];
    } else if (/^https?:\/\//i.test(value)) {
      return ""; // some other website
    } else if (value.startsWith("/")) {
      value = value.slice(1);
    }

    const segment = value.split("/").filter(Boolean)[0] || "";
    const handle = segment.replace(/^@/, "").trim();
    if (!handle || BLOCKED_SEGMENTS.has(handle.toLowerCase())) return "";
    return handle;
  }

  /** Normalize a configured API base URL (drops trailing slashes). */
  function normalizeApiBase(base) {
    const value = (base || "").trim();
    if (!value) return "";
    return value.replace(/\/+$/, "");
  }

  /** The request body sent to the backend. */
  function buildLeadPayload(handle) {
    return { username: handle, source: "extension" };
  }

  /** Map an HTTP status + parsed body to a clear UI state. */
  function classifyResponse(status, body) {
    const leadId = body && body.lead ? body.lead.lead_id : undefined;
    if (status === 201) {
      return { state: "created", message: "Added to the pipeline.", leadId };
    }
    if (status === 200) {
      return { state: "duplicate", message: "Already in the pipeline.", leadId };
    }
    if (status === 401 || status === 403) {
      return { state: "auth", message: "Invalid or missing API key." };
    }
    if (status === 422) {
      const detail = body && body.detail ? JSON.stringify(body.detail) : "Invalid profile URL.";
      return { state: "invalid", message: detail };
    }
    if (status === 503) {
      return { state: "error", message: "Backend storage is unavailable." };
    }
    return { state: "error", message: `Request failed (${status}).` };
  }

  /**
   * Submit a handle/profile URL to the backend API.
   * `fetchImpl` is injectable for tests.
   */
  async function submitLead({ apiBaseUrl, apiKey, username, fetchImpl }) {
    const base = normalizeApiBase(apiBaseUrl || DEFAULT_API_BASE);
    if (!base) {
      return { state: "config", message: "Set the API URL in the extension settings." };
    }

    const handle = extractHandle(username);
    if (!handle) {
      return { state: "invalid", message: "Open an Instagram profile first." };
    }

    const headers = { "content-type": "application/json", accept: "application/json" };
    if (apiKey && apiKey.trim()) headers["x-api-key"] = apiKey.trim();

    const doFetch = fetchImpl || (typeof fetch !== "undefined" ? fetch : null);
    if (!doFetch) {
      return { state: "network", message: "Networking is unavailable." };
    }

    let response;
    try {
      response = await doFetch(`${base}/api/v1/leads`, {
        method: "POST",
        headers,
        body: JSON.stringify(buildLeadPayload(handle)),
      });
    } catch (error) {
      return { state: "network", message: "Network error — is the API running?" };
    }

    let body = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    return classifyResponse(response.status, body);
  }

  return {
    DEFAULT_API_BASE,
    BLOCKED_SEGMENTS,
    buildLeadPayload,
    classifyResponse,
    extractHandle,
    normalizeApiBase,
    submitLead,
  };
});
