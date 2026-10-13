/**
 * Content script: adds a single "Add to GTM" button on Instagram profile pages
 * and submits the handle to the backend via the service worker.
 *
 * Minimal by design: it reads only the current URL (no bio/follower scraping)
 * and never touches Google Sheets or provider APIs directly.
 */
(function () {
  const BUTTON_ID = "synpo-add-lead";
  const ACTION_TEXTS = ["follow", "following", "requested", "message"];

  const LABELS = {
    idle: "Add to GTM",
    saving: "Saving…",
    created: "Added ✓",
    duplicate: "Already added",
    auth: "Check API key",
    config: "Set API URL",
    invalid: "Invalid profile",
    network: "Offline — retry",
    error: "Failed — retry",
  };

  function currentHandle() {
    return SynpoLib.extractHandle(window.location.href);
  }

  function setButtonState(button, state, title) {
    button.textContent = LABELS[state] || LABELS.error;
    button.dataset.state = state;
    button.title = title || "";
    button.disabled = state === "saving";
  }

  function findActionRow() {
    const buttons = Array.from(document.querySelectorAll("header button, main button"));
    const anchor =
      buttons.find((button) =>
        ACTION_TEXTS.includes((button.textContent || "").trim().toLowerCase()),
      ) || null;
    if (!anchor) return null;
    return anchor.parentElement && anchor.parentElement.parentElement
      ? anchor.parentElement.parentElement
      : anchor.parentElement;
  }

  function injectStyles() {
    if (document.getElementById("synpo-styles")) return;
    const style = document.createElement("style");
    style.id = "synpo-styles";
    style.textContent = `
      #${BUTTON_ID} {
        border: 0 !important; border-radius: 8px !important;
        padding: 0 16px !important; min-height: 40px !important;
        background: #22c98a !important; color: #04120b !important;
        font: inherit !important; font-weight: 700 !important;
        cursor: pointer !important; white-space: nowrap !important;
        margin-left: 8px !important;
      }
      #${BUTTON_ID}:hover { background: #4ade9f !important; }
      #${BUTTON_ID}[data-state="saving"] { background: #f5b544 !important; cursor: wait !important; }
      #${BUTTON_ID}[data-state="created"] { background: #12a873 !important; }
      #${BUTTON_ID}[data-state="duplicate"] { background: #3b5178 !important; color: #eef3fb !important; }
      #${BUTTON_ID}[data-state="auth"],
      #${BUTTON_ID}[data-state="config"],
      #${BUTTON_ID}[data-state="invalid"],
      #${BUTTON_ID}[data-state="error"],
      #${BUTTON_ID}[data-state="network"] { background: #f2637f !important; color: #1a0309 !important; }
      #${BUTTON_ID}[data-placement="fixed"] {
        position: fixed !important; top: 148px !important; right: 24px !important;
        z-index: 2147483647 !important; box-shadow: 0 12px 30px rgba(0,0,0,0.35) !important;
      }
    `;
    document.documentElement.appendChild(style);
  }

  async function onSubmit(button) {
    if (button.dataset.busy === "1") return; // ignore repeated clicks
    button.dataset.busy = "1";
    setButtonState(button, "saving");

    let result;
    try {
      result = await chrome.runtime.sendMessage({
        type: "synpoSubmitLead",
        username: window.location.href,
      });
    } catch (error) {
      result = { state: "error", message: "Extension error." };
    }

    setButtonState(button, result && result.state ? result.state : "error", result && result.message);

    setTimeout(() => {
      button.dataset.busy = "0";
      if (button.dataset.state !== "created" && button.dataset.state !== "duplicate") {
        setButtonState(button, "idle");
      }
    }, 2500);
  }

  function ensureButton() {
    const handle = currentHandle();
    const existing = document.getElementById(BUTTON_ID);

    if (!handle) {
      if (existing) existing.remove();
      return;
    }

    injectStyles();
    let button = existing;
    if (!button) {
      button = document.createElement("button");
      button.id = BUTTON_ID;
      button.type = "button";
      button.dataset.busy = "0";
      setButtonState(button, "idle");
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        onSubmit(button);
      });
    }

    const row = findActionRow();
    if (row && !row.contains(button)) {
      button.dataset.placement = "inline";
      row.appendChild(button);
    } else if (!row) {
      button.dataset.placement = "fixed";
      if (!document.body.contains(button)) document.body.appendChild(button);
    }
  }

  let lastPath = "";
  function tick() {
    if (window.location.pathname !== lastPath) lastPath = window.location.pathname;
    ensureButton();
  }

  tick();
  setInterval(tick, 800);
})();
