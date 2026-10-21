/**
 * Service worker: the only place that talks to the backend API.
 *
 * Reads the user-configured API base URL + key from chrome.storage.local,
 * submits captures (with optional snapshots) via SynpoLib, and returns a clear
 * result to the caller.
 */
importScripts("lib.js");

const STORAGE_KEYS = ["apiBaseUrl", "apiKey"];

async function getConfig() {
  const stored = await chrome.storage.local.get(STORAGE_KEYS);
  return {
    apiBaseUrl: stored.apiBaseUrl || SynpoLib.DEFAULT_API_BASE,
    apiKey: stored.apiKey || "",
  };
}

async function handleSubmit(message) {
  const config = await getConfig();
  return SynpoLib.submitLead({
    apiBaseUrl: config.apiBaseUrl,
    apiKey: config.apiKey,
    username: message.username,
    requestId: message.requestId,
    snapshot: message.snapshot,
  });
}

async function handleCheckConnection() {
  const config = await getConfig();
  const base = SynpoLib.normalizeApiBase(config.apiBaseUrl || SynpoLib.DEFAULT_API_BASE);
  if (!base) return { ok: false, state: "config", message: "Set the backend URL first." };

  const headers = { accept: "application/json" };
  if (config.apiKey && config.apiKey.trim()) headers["x-api-key"] = config.apiKey.trim();

  try {
    const response = await fetch(`${base}/api/v1/leads?limit=1`, { headers });
    return SynpoLib.classifyConnection({ status: response.status });
  } catch {
    return SynpoLib.classifyConnection({ error: true });
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message) return false;

  if (message.type === "synpoSubmitLead") {
    handleSubmit(message)
      .then((result) => sendResponse(result))
      .catch((error) =>
        sendResponse({ state: "error", message: String(error && error.message ? error.message : error) }),
      );
    return true;
  }

  if (message.type === "synpoCheckConnection") {
    handleCheckConnection()
      .then((result) => sendResponse(result))
      .catch((error) =>
        sendResponse({ ok: false, state: "error", message: String(error && error.message ? error.message : error) }),
      );
    return true;
  }

  return false;
});
