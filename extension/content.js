/**
 * Content script: reads the open Instagram profile into a snapshot, discovers
 * verified accounts in the "Suggested for you" rail, and adds a single
 * "Add to GTM" button on profile pages.
 *
 * The DOM traversal here is intentionally thin: it reduces the page to plain
 * descriptors and hands them to the pure helpers in `lib.js` (SynpoLib), which
 * are unit-tested without a browser. No page content is sent anywhere except
 * the user's own backend, and only after an explicit click.
 */
(function () {
  const BUTTON_ID = "synpo-add-lead";
  const ACTION_TEXTS = ["follow", "following", "requested", "message"];

  const LABELS = {
    idle: "Add to GTM",
    saving: "Saving…",
    created: "Added ✓",
    duplicate: "Already added",
    updated: "Updated ✓",
    auth: "Check API key",
    config: "Set API URL",
    invalid: "Invalid profile",
    network: "Offline — retry",
    error: "Failed — retry",
  };

  const requestIds = new Map();

  function requestIdFor(handle) {
    const key = (handle || "").toLowerCase();
    if (!requestIds.has(key)) requestIds.set(key, SynpoLib.makeRequestId());
    return requestIds.get(key);
  }

  function currentHandle() {
    return SynpoLib.extractHandle(window.location.href);
  }

  // -- snapshot extraction -------------------------------------------------

  function readMetaDescription() {
    return (
      document.querySelector('meta[name="description"]')?.content ||
      document.querySelector('meta[property="og:description"]')?.content ||
      ""
    );
  }

  function readDisplayName(username) {
    const candidates = [];

    const titleMatch = (document.title || "").match(/^(.+?)\s+\(@([^)]+)\)/);
    if (titleMatch && titleMatch[2]?.toLowerCase() === username.toLowerCase()) {
      candidates.push(titleMatch[1]);
    }

    const metaTitle = document.querySelector('meta[property="og:title"]')?.content || "";
    const metaMatch = metaTitle.match(/^(.+?)\s+\(@([^)]+)\)/);
    if (metaMatch && metaMatch[2]?.toLowerCase() === username.toLowerCase()) {
      candidates.push(metaMatch[1]);
    }

    const header = document.querySelector("header");
    for (const node of Array.from(header?.querySelectorAll("h1, h2, span") || [])) {
      candidates.push((node.textContent || "").trim());
    }

    // Drops pure numbers ("522", "2,118") and stat words ("posts", "followers").
    return SynpoLib.pickDisplayName(candidates, { username });
  }

  function isVerifiedProfile() {
    const header = document.querySelector("header");
    if (!header) return false;
    const labels = Array.from(header.querySelectorAll("[aria-label], [title]")).map(
      (element) => `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""}`,
    );
    if (SynpoLib.isVerifiedText(labels)) return true;
    const markup = Array.from(header.querySelectorAll("svg")).map((svg) => svg.outerHTML || "");
    return SynpoLib.isVerifiedMarkup(markup);
  }

  function readBioLines(username, displayName) {
    const header = document.querySelector("header");
    if (!header) return [];

    // Primary: parse the header HTML and strip anchors/buttons/counts first, so
    // injected buttons and the "Suggested for you" rail never leak into the bio.
    const parsed = SynpoLib.parseProfileHtml(header.innerHTML || "", { username, displayName });
    if (parsed.bioLines.length) return parsed.bioLines;

    // Fallback: plain bio spans only (no anchors, buttons, counts or nav).
    const spans = Array.from(header.querySelectorAll('span[dir="auto"]')).filter(
      (element) =>
        !element.closest('button, a[role="button"], nav, [role="navigation"], ul, a'),
    );
    const lines = spans
      .flatMap((element) => (element.textContent || "").split("\n"))
      .map((line) => line.trim())
      .filter(Boolean);
    return SynpoLib.filterBioLines(lines, { username, displayName });
  }

  function readExternalUrls(username, displayName) {
    const header = document.querySelector("header");
    if (!header) return [];
    const parsed = SynpoLib.parseProfileHtml(header.innerHTML || "", { username, displayName });
    const domLinks = Array.from(header.querySelectorAll("a[href]")).map((link) => link.href || "");
    return SynpoLib.normalizeExternalUrls([...parsed.externalUrls, ...domLinks]);
  }

  function firstMatch(text, pattern) {
    const match = text.match(pattern);
    return match ? match[1].trim() : "";
  }

  function readProfileSnapshot() {
    const username = currentHandle();
    if (!username) return null;

    const header = document.querySelector("header");
    const combined = `${header?.innerText || ""}\n${readMetaDescription()}`;
    const parsed = SynpoLib.parseProfileHtml(header?.innerHTML || "", { username });
    const displayName = readDisplayName(username) || parsed.displayName;

    return SynpoLib.buildSnapshot(
      {
        displayName,
        isVerified: isVerifiedProfile(),
        bioLines: readBioLines(username, displayName),
        externalUrls: readExternalUrls(username, displayName),
        followersText: firstMatch(combined, /([\d,.]+\s*[KMB]?)\s+followers/i),
        followingText: firstMatch(combined, /([\d,.]+\s*[KMB]?)\s+following/i),
        postsText: firstMatch(combined, /([\d,.]+\s*[KMB]?)\s+posts/i),
      },
      {
        sourceUrl: `https://www.instagram.com/${username}/`,
        capturedAt: new Date().toISOString(),
        parserVersion: SynpoLib.PARSER_VERSION,
      },
    );
  }

  // -- verified discovery (ported from the previous extension) -------------

  function profileUsernameFromHref(href) {
    try {
      const url = new URL(href, window.location.origin);
      if (!url.hostname.endsWith("instagram.com")) return "";
      return SynpoLib.extractHandle(url.pathname);
    } catch {
      return "";
    }
  }

  function findSuggestedSection() {
    const heading = Array.from(document.querySelectorAll("main span, main div, main h2, main h3")).find(
      (element) => (element.textContent || "").trim().toLowerCase() === "suggested for you",
    );
    if (!heading) return { heading: null, section: null };

    let section = heading.parentElement;
    for (let depth = 0; section && depth < 8; depth += 1) {
      const text = section.innerText || "";
      const followCount = (text.match(/\bFollow\b/g) || []).length;
      const rect = section.getBoundingClientRect();
      if (followCount >= 2 && rect.height >= 160 && rect.width >= 300) break;
      section = section.parentElement;
    }
    return { heading, section };
  }

  function findSuggestionCardFromDismiss(dismissButton) {
    let current = dismissButton;
    for (let depth = 0; current && depth < 10; depth += 1) {
      const rect = current.getBoundingClientRect();
      const text = current.innerText || "";
      const hasFollow = /\bFollow\b/i.test(text);
      const links = Array.from(
        current.querySelectorAll('a[href^="/"], a[href^="https://www.instagram.com/"]'),
      )
        .map((link) => profileUsernameFromHref(link.href))
        .filter((username) => username && username.toLowerCase() !== "follow");
      if (rect.width >= 120 && rect.width <= 260 && rect.height >= 160 && hasFollow && links.length) {
        return { card: current, username: links[0] };
      }
      current = current.parentElement;
    }
    return null;
  }

  function cardFullName(card, username) {
    return (
      (card.innerText || "")
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .filter((line) => !/^follow$/i.test(line))
        .filter((line) => line !== "×")
        .filter((line) => line.toLowerCase() !== username.toLowerCase())[0] || ""
    );
  }

  function cardDescriptor(card, username) {
    const rect = card.getBoundingClientRect();
    const text = card.innerText || "";
    return {
      username,
      fullName: cardFullName(card, username),
      labels: Array.from(card.querySelectorAll("[aria-label], [title]")).map(
        (element) => `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""}`,
      ),
      svgMarkup: Array.from(card.querySelectorAll("svg")).map((svg) => svg.outerHTML || ""),
      text,
      width: rect.width,
      height: rect.height,
      hasFollow: /\bFollow\b/i.test(text),
      linkCount: card.querySelectorAll('a[href^="/"], a[href^="https://www.instagram.com/"]').length,
    };
  }

  function collectSuggestedDescriptors() {
    const { section } = findSuggestedSection();
    if (!section) return [];
    const descriptors = [];
    const dismissButtons = Array.from(
      section.querySelectorAll('button[aria-label="Dismiss"], [role="button"][aria-label="Dismiss"]'),
    );
    for (const dismissButton of dismissButtons) {
      const match = findSuggestionCardFromDismiss(dismissButton);
      if (!match) continue;
      descriptors.push(cardDescriptor(match.card, match.username));
    }
    return descriptors;
  }

  /** Returns verified accounts found on the current page, deduplicated. */
  function findAllVerifiedOnPage() {
    const { section } = findSuggestedSection();
    const accounts = SynpoLib.associateSuggestedAccounts(collectSuggestedDescriptors());
    const verified = accounts.filter((account) => account.verified);
    return {
      supported: Boolean(section),
      discovered: accounts.length,
      accounts: verified.map((account) => ({
        ...account,
        requestId: requestIdFor(account.username),
      })),
    };
  }

  // -- single-profile button ----------------------------------------------

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
      #${BUTTON_ID}[data-state="created"],
      #${BUTTON_ID}[data-state="updated"] { background: #12a873 !important; }
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

    const handle = currentHandle();
    const snapshot = readProfileSnapshot();
    let result;
    try {
      result = await chrome.runtime.sendMessage({
        type: "synpoSubmitLead",
        username: window.location.href,
        requestId: requestIdFor(handle),
        snapshot,
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

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "synpoReadSnapshot") {
      sendResponse({ ok: true, snapshot: readProfileSnapshot() });
      return true;
    }
    if (message?.type === "synpoFindVerified") {
      try {
        sendResponse({ ok: true, ...findAllVerifiedOnPage() });
      } catch (error) {
        sendResponse({ ok: false, error: String(error && error.message ? error.message : error) });
      }
      return true;
    }
    return false;
  });

  let lastPath = "";
  function tick() {
    if (window.location.pathname !== lastPath) lastPath = window.location.pathname;
    ensureButton();
  }

  tick();
  setInterval(tick, 800);
})();
