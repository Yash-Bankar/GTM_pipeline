const handleEl = document.getElementById("handle");
const statusEl = document.getElementById("status");
const addButton = document.getElementById("addButton");
const apiBaseInput = document.getElementById("apiBaseUrl");
const apiKeyInput = document.getElementById("apiKey");
const saveButton = document.getElementById("saveSettings");

let currentHandle = "";

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(["apiBaseUrl", "apiKey"]);
  apiBaseInput.value = stored.apiBaseUrl || SynpoLib.DEFAULT_API_BASE;
  apiKeyInput.value = stored.apiKey || "";
}

async function saveSettings() {
  await chrome.storage.local.set({
    apiBaseUrl: SynpoLib.normalizeApiBase(apiBaseInput.value) || SynpoLib.DEFAULT_API_BASE,
    apiKey: apiKeyInput.value.trim(),
  });
  setStatus("Settings saved.", "ok");
}

async function initialize() {
  await loadSettings();
  const tab = await getActiveTab();
  currentHandle = SynpoLib.extractHandle(tab ? tab.url : "");

  if (!currentHandle) {
    handleEl.textContent = "Not a profile";
    addButton.disabled = true;
    setStatus("Open an Instagram profile page first.", "warn");
    return;
  }

  handleEl.textContent = `@${currentHandle}`;
  addButton.disabled = false;
  setStatus("Ready to add this profile.", "ok");
}

async function addCurrent() {
  if (!currentHandle) {
    setStatus("No profile detected.", "warn");
    return;
  }
  addButton.disabled = true;
  setStatus("Saving…");

  let result;
  try {
    result = await chrome.runtime.sendMessage({
      type: "synpoSubmitLead",
      username: `https://www.instagram.com/${currentHandle}/`,
    });
  } catch (error) {
    result = { state: "error", message: "Extension error." };
  }

  const kind =
    result.state === "created" ? "ok" : result.state === "duplicate" ? "warn" : "error";
  setStatus(result.message || "Done.", kind);
  addButton.disabled = false;
}

addButton.addEventListener("click", addCurrent);
saveButton.addEventListener("click", saveSettings);
initialize();
