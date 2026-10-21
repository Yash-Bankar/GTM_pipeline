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
const connectionResult = document.getElementById("connectionResult");
const backendLabel = document.getElementById("backendLabel");
const queueSection = document.getElementById("queueSection");
const queueList = document.getElementById("queueList");
const queueCount = document.getElementById("queueCount");
const queueNote = document.getElementById("queueNote");

const QUEUE_KEY = "captureQueue";

let currentHandle = "";
let currentSnapshot = null;
let verifiedAccounts = [];
let verifiedSupported = false;
let queue = [];

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

function setConnection(message, kind = "") {
  if (!message) {
    connectionResult.hidden = true;
    connectionResult.textContent = "";
    return;
  }
  connectionResult.hidden = false;
  connectionResult.textContent = message;
  connectionResult.className = `status ${kind}`;
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

// -- settings --------------------------------------------------------------

async function loadSettings() {
  const stored = await chrome.storage.local.get(["apiBaseUrl", "apiKey"]);
  const base = stored.apiBaseUrl || SynpoLib.DEFAULT_API_BASE;
  apiBaseInput.value = base;
  apiKeyInput.value = stored.apiKey || "";
  backendLabel.textContent = `Backend: ${SynpoLib.normalizeApiBase(base) || base}`;
}

async function saveSettings() {
  const base = SynpoLib.normalizeApiBase(apiBaseInput.value) || SynpoLib.DEFAULT_API_BASE;
  await chrome.storage.local.set({ apiBaseUrl: base, apiKey: apiKeyInput.value.trim() });
  backendLabel.textContent = `Backend: ${base}`;
  setConnection("");
  setStatus("Settings saved.", "ok");
}

async function checkConnection() {
  setConnection("Testing connection…");
  let result;
  try {
    result = await chrome.runtime.sendMessage({ type: "synpoCheckConnection" });
  } catch {
    result = SynpoLib.classifyConnection({ error: true });
  }
  const kind =
    result.state === "connected" ? "ok" : result.state === "error" ? "error" : "warn";
  setConnection(result.message || "Done.", kind);
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

// -- pending queue ---------------------------------------------------------

async function loadQueue() {
  const stored = await chrome.storage.local.get(QUEUE_KEY);
  queue = SynpoLib.normalizeQueue(stored[QUEUE_KEY] || []);
  renderQueue();
}

async function saveQueue(next) {
  queue = SynpoLib.normalizeQueue(next);
  if (queue.length) await chrome.storage.local.set({ [QUEUE_KEY]: queue });
  else await chrome.storage.local.remove(QUEUE_KEY);
  renderQueue();
}

function renderQueue() {
  const full = SynpoLib.isQueueFull(queue);
  queueSection.hidden = queue.length === 0;
  queueCount.textContent = `${queue.length}/${SynpoLib.QUEUE_LIMIT}`;
  queueList.replaceChildren();

  for (const item of queue) {
    const li = document.createElement("li");
    li.className = "queue-item";

    const info = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = `@${item.username}`;
    const meta = document.createElement("span");
    meta.className = "muted";
    meta.textContent = item.lastError ? `Failed: ${item.lastError}` : "Not acknowledged";
    info.append(name, meta);

    const actions = document.createElement("div");
    actions.className = "queue-actions";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "mini";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => retryItem(item.requestId));
    const discard = document.createElement("button");
    discard.type = "button";
    discard.className = "mini secondary";
    discard.textContent = "Discard";
    discard.addEventListener("click", () => discardItem(item.requestId));
    actions.append(retry, discard);

    li.append(info, actions);
    queueList.append(li);
  }

  queueNote.hidden = !full;
  if (full) queueNote.textContent = SynpoLib.queueCapacityMessage();

  addButton.disabled = !currentHandle || full;
  addAllButton.disabled = full || verifiedAccounts.length === 0;
  retryButton.hidden = queue.length === 0;
}

async function enqueuePending(item) {
  const result = SynpoLib.enqueueCapture(queue, item);
  if (result.accepted) {
    await saveQueue(result.queue);
  } else if (result.reason === "queue_full") {
    queueNote.hidden = false;
    queueNote.textContent = SynpoLib.queueCapacityMessage();
  }
  return result;
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

function failedItem({ requestId, username, snapshot, message }) {
  return {
    requestId,
    username,
    snapshot,
    status: "failed",
    lastError: message || "Not saved",
    createdAt: new Date().toISOString(),
  };
}

// -- submission ------------------------------------------------------------

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
  if (SynpoLib.isQueueFull(queue)) {
    setStatus(SynpoLib.queueCapacityMessage(), "warn");
    return;
  }
  addButton.disabled = true;
  setStatus("Saving…");

  const requestId = SynpoLib.makeRequestId();
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

  if (SynpoLib.isAcknowledgedSave(result.state)) {
    // A successful acknowledgement removes any older pending copy.
    await saveQueue(SynpoLib.removeCapture(queue, requestId));
    const kind = result.state === "duplicate" ? "warn" : "ok";
    setStatus(result.message || "Done.", kind);
  } else {
    await enqueuePending(
      failedItem({
        requestId,
        username: currentHandle,
        snapshot: currentSnapshot,
        message: result.message,
      }),
    );
    setStatus(result.message || "Not saved. Retry from the pending list.", "error");
  }
  addButton.disabled = !currentHandle || SynpoLib.isQueueFull(queue);
}

async function retryItem(requestId) {
  const item = queue.find((entry) => entry.requestId === requestId);
  if (!item) return null;
  let result;
  try {
    result = await submitSingle(SynpoLib.retryPayload(item));
  } catch {
    result = { state: "error", message: "Extension error." };
  }

  if (SynpoLib.isAcknowledgedSave(result.state)) {
    await saveQueue(SynpoLib.removeCapture(queue, requestId));
  } else {
    await saveQueue(
      SynpoLib.markCapture(queue, requestId, {
        status: "failed",
        lastError: result.message || "Not saved",
        updatedAt: new Date().toISOString(),
      }),
    );
  }
  return result;
}

async function discardItem(requestId) {
  await saveQueue(SynpoLib.removeCapture(queue, requestId));
  setStatus("Pending save discarded.", "warn");
}

async function retryAll() {
  if (!queue.length) return;
  retryButton.disabled = true;
  setStatus("Retrying pending saves…");
  const ids = queue.map((item) => item.requestId);
  let ok = 0;
  let failed = 0;
  for (const requestId of ids) {
    const result = await retryItem(requestId);
    if (result && SynpoLib.isAcknowledgedSave(result.state)) ok += 1;
    else failed += 1;
  }
  retryButton.disabled = false;
  setStatus(
    `Retried ${ids.length}: ${ok} saved, ${failed} still pending.`,
    failed ? "warn" : "ok",
  );
}

// -- verified batch --------------------------------------------------------

async function runBulk(items, { retrying = false } = {}) {
  addAllButton.disabled = true;
  setBatch(retrying ? "Retrying…" : "Adding…");

  // Build each snapshot once so a queued retry sends the exact same payload
  // (and therefore the same request-id hash) as the original attempt.
  const prepared = items.map((item) => ({
    ...item,
    snapshot: item.snapshot || minimalSnapshot(item),
  }));

  const summary = await SynpoLib.runBulkSubmit({
    accounts: prepared,
    submit: (account) =>
      submitSingle({
        username: account.username,
        requestId: account.requestId,
        snapshot: account.snapshot,
      }),
    onProgress: (progress) => {
      const done = progress.added + progress.existing + progress.skipped + progress.failed;
      setBatch(`Working… ${done}/${progress.total}`);
    },
  });

  const handled = new Set(["created", "duplicate", "updated", "skipped", "invalid"]);
  const failedItems = prepared.filter((item) => {
    const found = summary.results.find((result) => result.username === item.username);
    return !found || !handled.has(found.state);
  });

  const queueFull = [];
  for (const item of failedItems) {
    const found = summary.results.find((result) => result.username === item.username);
    const result = await enqueuePending(
      failedItem({
        requestId: item.requestId,
        username: item.username,
        snapshot: item.snapshot,
        message: found && found.message,
      }),
    );
    if (result.reason === "queue_full") queueFull.push(item.username);
  }

  const kind = summary.failed || queueFull.length ? "error" : "ok";
  const capacityNote = queueFull.length
    ? ` ${queueFull.length} could not be queued: ${SynpoLib.queueCapacityMessage()}`
    : "";
  setBatch(
    `Added ${summary.added} · Already saved ${summary.existing} · Skipped ${summary.skipped} · Failed ${summary.failed}.${capacityNote}`,
    kind,
  );
  addAllButton.disabled = SynpoLib.isQueueFull(queue) || verifiedAccounts.length === 0;
}

async function addAllVerified() {
  if (!verifiedAccounts.length) {
    setBatch("No verified accounts detected on this page.", "warn");
    return;
  }
  if (SynpoLib.isQueueFull(queue)) {
    setBatch(SynpoLib.queueCapacityMessage(), "warn");
    return;
  }
  const items = verifiedAccounts.map((account) => ({
    username: account.username,
    fullName: account.fullName,
    requestId: account.requestId,
  }));
  await runBulk(items);
}

// -- initialize ------------------------------------------------------------

async function initialize() {
  await loadSettings();
  await loadQueue();

  const tab = await getActiveTab();
  currentHandle = SynpoLib.extractHandle(tab ? tab.url : "");

  if (!currentHandle) {
    handleEl.textContent = "Not a profile";
    addButton.disabled = true;
    addAllButton.hidden = true;
    setStatus(
      queue.length
        ? "Open an Instagram profile page. Pending saves are listed below."
        : "Open an Instagram profile page first.",
      "warn",
    );
    return;
  }

  handleEl.textContent = `@${currentHandle}`;
  addButton.disabled = SynpoLib.isQueueFull(queue);
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
      addAllButton.disabled =
        SynpoLib.isQueueFull(queue) || verifiedAccounts.length === 0;
      addAllButton.textContent = `Add All Verified (${verifiedAccounts.length})`;
      if (!verifiedAccounts.length) addAllButton.title = "No verified accounts in the Suggested rail.";
    } else {
      addAllButton.hidden = true;
    }
  }
}

addButton.addEventListener("click", addCurrent);
addAllButton.addEventListener("click", addAllVerified);
retryButton.addEventListener("click", retryAll);
saveButton.addEventListener("click", saveSettings);
checkButton.addEventListener("click", checkConnection);
initialize();
