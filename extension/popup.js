const handleEl = document.getElementById("handle");
const snapshotEl = document.getElementById("snapshot");
const statusEl = document.getElementById("status");
const batchEl = document.getElementById("batchResult");
const addButton = document.getElementById("addButton");
const addAllButton = document.getElementById("addAllButton");
const retryButton = document.getElementById("retryButton");
const apiBaseInput = document.getElementById("apiBaseUrl");
const apiKeyInput = document.getElementById("apiKey");
const saveButton = document.getElementById("saveSettings");
const checkButton = document.getElementById("checkConnection");

const PENDING_CAPTURE = "pendingCapture";
const PENDING_BATCH = "pendingBatch";

let currentHandle = "";
let currentSnapshot = null;
let verifiedAccounts = [];
let verifiedSupported = false;

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`;
}

function setBatch(message, kind = "") {
  if (!message) {
    batchEl.hidden = true;
    batchEl.textContent = "";
    return;
  }
  batchEl.hidden = false;
  batchEl.textContent = message;
  batchEl.className = `status ${kind}`;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function sendToTab(type) {
  const tab = await getActiveTab();
  if (!tab || !tab.id) return null;
  try {
    return await chrome.tabs.sendMessage(tab.id, { type });
  } catch {
    return null; // content script not present (e.g. page not loaded/refreshed)
  }
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

async function checkConnection() {
  setStatus("Checking connection…");
  let result;
  try {
    result = await chrome.runtime.sendMessage({ type: "synpoCheckConnection" });
  } catch {
    result = { ok: false, message: "Extension error." };
  }
  setStatus(result && result.message ? result.message : "Done.", result && result.ok ? "ok" : "error");
}

// -- snapshot preview ------------------------------------------------------

function fieldRow(label, value, missing) {
  const row = document.createElement("div");
  row.className = "snap-row";
  const key = document.createElement("span");
  key.className = "snap-label";
  key.textContent = label;
  const val = document.createElement("span");
  val.className = missing ? "snap-value missing" : "snap-value";
  val.textContent = missing ? "unknown" : value;
  row.append(key, val);
  return row;
}

function formatCount(observation) {
  if (!observation || observation.value === null || observation.value === undefined) {
    return { text: "unknown", missing: true };
  }
  const display = observation.display ? `${observation.display} ` : "";
  const precision = observation.precision === "approximate" ? " (approx.)" : "";
  return { text: `${display}(${observation.value.toLocaleString()})${precision}`.trim(), missing: false };
}

function renderSnapshot(snapshot) {
  snapshotEl.replaceChildren();
  if (!snapshot) {
    snapshotEl.hidden = true;
    return;
  }
  snapshotEl.hidden = false;
  const missing = new Set(snapshot.missing_fields || []);

  const verified = document.createElement("div");
  verified.className = snapshot.is_verified ? "snap-verified" : "snap-unverified";
  verified.textContent = snapshot.is_verified ? "✓ Verified account" : "Not verified";
  snapshotEl.append(verified);

  snapshotEl.append(fieldRow("Display name", snapshot.display_name, missing.has("display_name")));

  const followers = formatCount(snapshot.followers);
  snapshotEl.append(fieldRow("Followers", followers.text, followers.missing));
  const following = formatCount(snapshot.following);
  snapshotEl.append(fieldRow("Following", following.text, following.missing));
  const posts = formatCount(snapshot.post_count);
  snapshotEl.append(fieldRow("Posts", posts.text, posts.missing));

  const bio = (snapshot.bio || "").slice(0, 140);
  snapshotEl.append(fieldRow("Bio", bio, missing.has("bio")));

  const links = snapshot.external_urls || [];
  snapshotEl.append(
    fieldRow("Links", links.length ? `${links.length} · ${links[0]}` : "", links.length === 0),
  );

  if (missing.size) {
    const note = document.createElement("div");
    note.className = "snap-missing";
    note.textContent = `Missing: ${Array.from(missing).join(", ")}`;
    snapshotEl.append(note);
  }
}

// -- pending capture storage ----------------------------------------------

async function loadPending() {
  const stored = await chrome.storage.local.get([PENDING_CAPTURE, PENDING_BATCH]);
  const pending = stored[PENDING_CAPTURE];
  const batch = stored[PENDING_BATCH] || [];
  const hasPending = Boolean(pending) || batch.length > 0;
  retryButton.hidden = !hasPending;
  return { pending: pending || null, batch };
}

async function savePendingCapture(capture) {
  if (capture) await chrome.storage.local.set({ [PENDING_CAPTURE]: capture });
  else await chrome.storage.local.remove(PENDING_CAPTURE);
}

async function savePendingBatch(items) {
  if (items && items.length) await chrome.storage.local.set({ [PENDING_BATCH]: items });
  else await chrome.storage.local.remove(PENDING_BATCH);
}

function newRequestId() {
  return SynpoLib.makeRequestId();
}

function minimalSnapshot(account) {
  return SynpoLib.buildSnapshot(
    { displayName: account.fullName || "", isVerified: true },
    {
      sourceUrl: `https://www.instagram.com/${account.username}/`,
      capturedAt: new Date().toISOString(),
      parserVersion: SynpoLib.PARSER_VERSION,
    },
  );
}

// -- single submission -----------------------------------------------------

async function submitSingle({ username, requestId, snapshot }) {
  return chrome.runtime.sendMessage({
    type: "synpoSubmitLead",
    username,
    requestId,
    snapshot,
  });
}

async function addCurrent() {
  if (!currentHandle) {
    setStatus("No profile detected.", "warn");
    return;
  }
  addButton.disabled = true;
  setStatus("Saving…");

  const requestId = newRequestId();
  let result;
  try {
    result = await submitSingle({
      username: `https://www.instagram.com/${currentHandle}/`,
      requestId,
      snapshot: currentSnapshot,
    });
  } catch {
    result = { state: "error", message: "Extension error." };
  }

  if (result.state === "network") {
    // Keep the exact payload + request id so a retry cannot double-submit.
    await savePendingCapture({
      username: currentHandle,
      requestId,
      snapshot: currentSnapshot,
      savedAt: new Date().toISOString(),
    });
    retryButton.hidden = false;
    setStatus("Not saved. Check the connection and retry.", "error");
  } else {
    await savePendingCapture(null);
    const kind =
      result.state === "created" || result.state === "updated"
        ? "ok"
        : result.state === "duplicate"
          ? "warn"
          : "error";
    setStatus(result.message || "Done.", kind);
  }
  addButton.disabled = false;
}

// -- bulk submission -------------------------------------------------------

async function runBulk(items, { retrying = false } = {}) {
  addAllButton.disabled = true;
  setBatch(retrying ? "Retrying…" : "Adding…");

  const summary = await SynpoLib.runBulkSubmit({
    accounts: items,
    submit: (account) =>
      submitSingle({
        username: account.username,
        requestId: account.requestId,
        snapshot: minimalSnapshot(account),
      }),
    onProgress: (progress) => {
      const done = progress.added + progress.existing + progress.skipped + progress.failed;
      setBatch(`Working… ${done}/${progress.total}`);
    },
  });

  const handled = new Set(["created", "duplicate", "updated", "skipped", "invalid", "config"]);
  const failedItems = items.filter((item) => {
    const found = summary.results.find((result) => result.username === item.username);
    return !found || !handled.has(found.state);
  });

  await savePendingBatch(failedItems);
  retryButton.hidden = failedItems.length === 0;

  const kind = summary.failed ? "error" : "ok";
  setBatch(
    `Added ${summary.added} · Already saved ${summary.existing} · Skipped ${summary.skipped} · Failed ${summary.failed}`,
    kind,
  );
  addAllButton.disabled = false;
}

async function addAllVerified() {
  if (!verifiedAccounts.length) {
    setBatch("No verified accounts detected on this page.", "warn");
    return;
  }
  const items = verifiedAccounts.map((account) => ({
    username: account.username,
    fullName: account.fullName,
    requestId: account.requestId,
  }));
  await runBulk(items);
}

async function retryPending() {
  const { pending, batch } = await loadPending();
  retryButton.hidden = true;
  setBatch("");

  if (batch.length) {
    await runBulk(batch, { retrying: true });
  } else if (pending) {
    addButton.disabled = true;
    let result;
    try {
      result = await submitSingle({
        username: `https://www.instagram.com/${pending.username}/`,
        requestId: pending.requestId,
        snapshot: pending.snapshot,
      });
    } catch {
      result = { state: "error", message: "Extension error." };
    }
    if (result.state !== "network") await savePendingCapture(null);
    else retryButton.hidden = false;
    setStatus(result.message || "Done.", result.state === "network" ? "error" : "ok");
    addButton.disabled = false;
  }
}

// -- initialize ------------------------------------------------------------

async function initialize() {
  await loadSettings();
  await loadPending();

  const tab = await getActiveTab();
  currentHandle = SynpoLib.extractHandle(tab ? tab.url : "");

  if (!currentHandle) {
    handleEl.textContent = "Not a profile";
    addButton.disabled = true;
    addAllButton.hidden = true;
    setStatus("Open an Instagram profile page first.", "warn");
    return;
  }

  handleEl.textContent = `@${currentHandle}`;
  addButton.disabled = false;
  setStatus("Reading the open profile…");

  const snapshotResult = await sendToTab("synpoReadSnapshot");
  if (snapshotResult && snapshotResult.ok && snapshotResult.snapshot) {
    currentSnapshot = snapshotResult.snapshot;
    renderSnapshot(currentSnapshot);
    setStatus("Ready to add this profile.", "ok");
  } else {
    currentSnapshot = null;
    renderSnapshot(null);
    setStatus("Profile details unavailable — refresh Instagram and retry.", "warn");
  }

  const verifiedResult = await sendToTab("synpoFindVerified");
  if (verifiedResult && verifiedResult.ok) {
    verifiedSupported = verifiedResult.supported;
    verifiedAccounts = verifiedResult.accounts || [];
    if (verifiedSupported) {
      addAllButton.hidden = false;
      addAllButton.disabled = verifiedAccounts.length === 0;
      addAllButton.textContent = `Add All Verified (${verifiedAccounts.length})`;
      if (!verifiedAccounts.length) addAllButton.title = "No verified accounts in the Suggested rail.";
    } else {
      addAllButton.hidden = true;
    }
  }
}

addButton.addEventListener("click", addCurrent);
addAllButton.addEventListener("click", addAllVerified);
retryButton.addEventListener("click", retryPending);
saveButton.addEventListener("click", saveSettings);
checkButton.addEventListener("click", checkConnection);
initialize();
