/**
 * Service worker: the only place that talks to the backend API.
 *
 * Reads the user-configured API base URL + key from chrome.storage.local,
 * submits leads via SynpoLib, and returns a clear result to the caller.
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
  });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "synpoSubmitLead") return false;

  handleSubmit(message)
    .then((result) => sendResponse(result))
    .catch((error) => sendResponse({ state: "error", message: String(error && error.message ? error.message : error) }));

  return true; // keep the message channel open for the async response
});
