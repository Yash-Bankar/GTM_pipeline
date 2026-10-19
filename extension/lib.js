/**
 * Shared, dependency-free helpers for the Synpo GTM extension.
 *
 * Loaded as a classic script (content/background/popup) via the global
 * `SynpoLib`, and as a CommonJS module in Node tests (`lib.test.js`).
 *
 * Contains no provider secrets. The DOM-facing code in `content.js` reduces the
 * page to plain descriptors; everything in this file is pure and unit-testable.
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
  const PARSER_VERSION = "1";

  // The suggested-rail card geometry the previous extension relied on.
  const CARD_MIN_WIDTH = 120;
  const CARD_MAX_WIDTH = 260;
  const CARD_MIN_HEIGHT = 160;

  const IGNORED_HOSTS = ["instagram.com", "facebook.com", "fb.com", "meta.com"];
  // Threads links are kept, canonicalized to https://www.threads.net/@handle.
  const THREADS_HOSTS = ["threads.net", "threads.com"];
  const TRACKING_KEYS = new Set(["igshid", "igsh", "fbclid", "gclid", "si", "xmt"]);

  // Lines that are page chrome rather than bio text. Compared case-insensitively
  // against the whole (trimmed) line.
  const BIO_DROP_EXACT = new Set([
    "follow",
    "following",
    "message",
    "requested",
    "more",
    "see all",
    "suggested for you",
    "add to gtm",
    "also from meta",
  ]);

  // Bare words that are never a display name (stats / UI labels).
  const STAT_WORDS = new Set([
    "posts",
    "post",
    "followers",
    "follower",
    "following",
    "follow",
    "message",
    "verified",
    "more",
  ]);

  const BIO_MAX = 2200;
  const MAX_EXTERNAL_URLS = 10;

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

  /**
   * Parse a count with display text into `{ value, display, precision }`.
   * `precision` is `exact` (plain integer), `approximate` (K/M/B suffix), or
   * `unknown`. Unknown never becomes zero (PRD §5.1).
   */
  function parseCompactCount(raw) {
    const display = (raw == null ? "" : String(raw)).trim();
    if (!display) return { value: null, display: "", precision: "unknown" };

    const normalized = display.replace(/[\s,]/g, "");
    const match = normalized.match(/^(\d+(?:\.\d+)?)([KMB])?$/i);
    if (!match) return { value: null, display, precision: "unknown" };

    const magnitude = Number(match[1]);
    if (!Number.isFinite(magnitude)) return { value: null, display, precision: "unknown" };

    const suffix = (match[2] || "").toUpperCase();
    if (!suffix) return { value: Math.round(magnitude), display, precision: "exact" };

    const multiplier = suffix === "K" ? 1e3 : suffix === "M" ? 1e6 : 1e9;
    return { value: Math.round(magnitude * multiplier), display, precision: "approximate" };
  }

  function isIgnoredHost(host) {
    return IGNORED_HOSTS.some((ignored) => host === ignored || host.endsWith("." + ignored));
  }

  function isThreadsHost(host) {
    return THREADS_HOSTS.some((threads) => host === threads || host.endsWith("." + threads));
  }

  /** Convert a Threads profile link to its canonical https://www.threads.net/@handle URL. */
  function canonicalThreadsUrl(parsed) {
    const segment = parsed.pathname.split("/").filter(Boolean)[0] || "";
    const handle = segment.replace(/^@/, "").trim();
    if (!handle || /^(t|share|search|login|explore|intent)$/i.test(handle)) return "";
    return `https://www.threads.net/@${handle}`;
  }

  /** Validate/clean one external URL: unwrap l.instagram redirects, drop trackers. */
  function cleanExternalUrl(url) {
    const raw = (url || "").trim();
    if (!raw) return "";
    let parsed;
    try {
      parsed = new URL(raw);
    } catch {
      return "";
    }

    const host = parsed.hostname.replace(/^www\./, "").toLowerCase();
    if (host === "l.instagram.com") {
      const target = parsed.searchParams.get("u");
      return target ? cleanExternalUrl(decodeURIComponent(target)) : "";
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
    if (isThreadsHost(host)) return canonicalThreadsUrl(parsed);
    if (isIgnoredHost(host)) return "";

    for (const key of Array.from(parsed.searchParams.keys())) {
      if (TRACKING_KEYS.has(key.toLowerCase()) || key.toLowerCase().startsWith("utm_")) {
        parsed.searchParams.delete(key);
      }
    }
    parsed.hash = "";
    return parsed.toString();
  }

  /** Clean, dedupe and cap a list of external URLs. */
  function normalizeExternalUrls(urls) {
    const result = [];
    const seen = new Set();
    for (const candidate of urls || []) {
      const cleaned = cleanExternalUrl(candidate);
      if (!cleaned) continue;
      const key = cleaned.replace(/\/$/, "");
      if (seen.has(key)) continue;
      seen.add(key);
      result.push(cleaned);
      if (result.length >= MAX_EXTERNAL_URLS) break;
    }
    return result;
  }

  /** Strip tags/entities from an HTML fragment, keeping <br> as newlines. */
  function stripTags(html) {
    return String(html == null ? "" : html)
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/&nbsp;/gi, " ")
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&quot;/gi, '"')
      .replace(/&#0*39;/gi, "'");
  }

  /** True when a line is only a count/stat (e.g. "2,118", "2.7M", "19.5M followers"). */
  function isStatLine(text) {
    const value = String(text == null ? "" : text).trim();
    if (!value) return true;
    if (/^[\d.,\s]+$/.test(value)) return true; // "2,118", "522", "65"
    if (/^[\d.,]+\s*[KMB]?$/i.test(value)) return true; // "2.7M", "19.5M"
    if (/\b(posts|followers|following)\b/i.test(value)) return true;
    return false;
  }

  /** True when text is a stat/UI word that must never be a display name. */
  function isStatString(text) {
    const value = String(text == null ? "" : text).trim();
    if (!value) return true;
    if (STAT_WORDS.has(value.toLowerCase())) return true;
    if (!/[a-z]/i.test(value)) return true; // pure numbers/symbols like "2,118"
    if (/\b(posts|followers|following)\b/i.test(value)) return true;
    return false;
  }

  /**
   * Pick the real display name from candidates, dropping stats. The first
   * handle occurrence (the username heading) is skipped; a later occurrence is
   * kept, because a creator's full name can equal their handle (e.g. "MrBeast").
   */
  function pickDisplayName(candidates, options) {
    const opts = options || {};
    const username = (opts.username || "").replace(/^@/, "").toLowerCase();
    let skippedHandle = false;
    for (const raw of candidates || []) {
      const text = String(raw == null ? "" : raw).trim();
      if (!text) continue;
      if (isStatString(text)) continue;
      if (username && text.toLowerCase().replace(/^@/, "") === username) {
        if (!skippedHandle) {
          skippedHandle = true;
          continue;
        }
        return text;
      }
      return text;
    }
    return "";
  }

  /**
   * Parse a profile header HTML string into
   * `{ displayName, bioLines, bio, externalUrls }`.
   *
   * Anchors, buttons, nav and the counts list are removed *before* reading the
   * bio so injected buttons and the "Suggested for you" rail never leak into it.
   * Anchors are read separately and cleaned into canonical URLs (Threads links
   * become `https://www.threads.net/@handle`). Pure — used by `content.js` and
   * by the HTML-fixture unit tests.
   */
  function parseProfileHtml(html, options) {
    const opts = options || {};
    let source = String(html == null ? "" : html)
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ");

    const urls = [];
    const anchorRe = /<a\b[^>]*\bhref\s*=\s*["']([^"']*)["'][^>]*>/gi;
    let match;
    while ((match = anchorRe.exec(source)) !== null) urls.push(match[1]);

    const withoutChrome = source
      .replace(/<a\b[\s\S]*?<\/a>/gi, " ")
      .replace(/<button\b[\s\S]*?<\/button>/gi, " ")
      .replace(/<nav\b[\s\S]*?<\/nav>/gi, " ")
      .replace(/<ul\b[\s\S]*?<\/ul>/gi, " ");

    const lines = [];
    const spanRe = /<span[^>]*\bdir\s*=\s*["']auto["'][^>]*>([\s\S]*?)<\/span>/gi;
    while ((match = spanRe.exec(withoutChrome)) !== null) {
      for (const part of stripTags(match[1]).split("\n")) {
        const trimmed = part.trim();
        if (trimmed) lines.push(trimmed);
      }
    }

    // Display name: headings and dir="auto" spans in DOM order. Chrome
    // (anchors, counts) is already removed, and stat strings are filtered out so
    // a count like "2,118" can never become the display name. Instagram renders
    // the username as a heading and the full name as a span, so the handle is
    // skipped and the next candidate is the real name.
    const nameCandidates = [];
    const nameRe =
      /<(h1|h2|h3)\b[^>]*>([\s\S]*?)<\/\1>|<span[^>]*\bdir\s*=\s*["']auto["'][^>]*>([\s\S]*?)<\/span>/gi;
    while ((match = nameRe.exec(withoutChrome)) !== null) {
      const raw = match[2] != null ? match[2] : match[3];
      nameCandidates.push(stripTags(raw).split("\n")[0]);
    }
    const displayName = pickDisplayName(nameCandidates, { username: opts.username });

    const bioLines = filterBioLines(lines, {
      username: opts.username,
      displayName,
    });
    return {
      displayName,
      bioLines,
      bio: bioLines.join("\n"),
      externalUrls: normalizeExternalUrls(urls),
    };
  }

  /**
   * Reduce candidate header lines to the creator's bio, dropping page chrome,
   * the injected extension button, the "Suggested for you" rail, counts,
   * follower-detail overlays and the handle/display name. Pure and testable.
   */
  function filterBioLines(lines, options) {
    const opts = options || {};
    const username = (opts.username || "").replace(/^@/, "").toLowerCase();
    const displayName = (opts.displayName || "").trim().toLowerCase();
    const seen = new Set();
    const result = [];

    for (const raw of lines || []) {
      const line = String(raw == null ? "" : raw).trim();
      if (!line) continue;
      const lower = line.toLowerCase();

      if (username && lower.replace(/^@/, "") === username) continue;
      if (displayName && lower === displayName) continue;
      if (BIO_DROP_EXACT.has(lower)) continue;
      if (/^(follow|following|message|requested|more)$/i.test(line)) continue;
      if (/^and\s+\d+\s+more$/i.test(line)) continue;
      if (/^\d+\s+more$/i.test(line)) continue;
      if (isStatLine(line)) continue;
      if (/^followed by\b/i.test(line)) continue;
      if (/^liked by\b/i.test(line)) continue;
      if (/^also from meta$/i.test(line)) continue;
      if (/suggested for you/i.test(line)) continue;
      if (line.includes("instagram.com")) continue;
      if (seen.has(lower)) continue;

      seen.add(lower);
      result.push(line);
      if (result.length >= 8) break;
    }
    return result;
  }

  /** A verified badge is exposed via aria-label/title text in the live DOM. */
  function isVerifiedText(texts) {
    return (texts || []).some((text) => String(text || "").toLowerCase().includes("verified"));
  }

  /** Fallback detection: the badge svg markup contains "verified". */
  function isVerifiedMarkup(markups) {
    return (markups || []).some((markup) => String(markup || "").toLowerCase().includes("verified"));
  }

  /**
   * Associate suggested-rail cards with accounts, porting the previous
   * extension's geometry + Follow/link heuristics. `descriptors` are plain
   * objects: `{ username, fullName, labels, svgMarkup, text, width, height,
   * hasFollow, linkCount }`. Duplicates are removed by normalized username.
   */
  function associateSuggestedAccounts(descriptors) {
    const seen = new Set();
    const accounts = [];
    for (const descriptor of descriptors || []) {
      if (!descriptor) continue;
      const handle = extractHandle(descriptor.username);
      if (!handle) continue;
      if (descriptor.width < CARD_MIN_WIDTH || descriptor.width > CARD_MAX_WIDTH) continue;
      if (descriptor.height < CARD_MIN_HEIGHT) continue;
      if (!descriptor.hasFollow) continue;
      if (!descriptor.linkCount) continue;

      const key = handle.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);

      accounts.push({
        username: handle,
        fullName: (descriptor.fullName || "").trim(),
        verified: isVerifiedText(descriptor.labels) || isVerifiedMarkup(descriptor.svgMarkup),
      });
    }
    return accounts;
  }

  /**
   * Build a profile snapshot from raw, already-read page text.
   * `raw`: `{ displayName, isVerified, bioLines, externalUrls, followersText,
   * followingText, postsText }`. `meta`: `{ sourceUrl, capturedAt,
   * parserVersion }`.
   */
  function buildSnapshot(raw, meta) {
    const source = raw || {};
    const info = meta || {};
    const bio = (source.bioLines || [])
      .map((line) => String(line || "").trim())
      .filter(Boolean)
      .join("\n")
      .slice(0, BIO_MAX);

    const followers = parseCompactCount(source.followersText);
    const following = parseCompactCount(source.followingText);
    const postCount = parseCompactCount(source.postsText);
    const externalUrls = normalizeExternalUrls(source.externalUrls);

    const snapshot = {
      display_name: (source.displayName || "").trim(),
      is_verified: Boolean(source.isVerified),
      bio,
      external_urls: externalUrls,
      followers,
      following,
      post_count: postCount,
      source_url: (info.sourceUrl || "").trim(),
      captured_at: (info.capturedAt || "").trim(),
      parser_version: (info.parserVersion || PARSER_VERSION).trim(),
      missing_fields: [],
    };

    const missing = [];
    if (!snapshot.display_name) missing.push("display_name");
    if (!snapshot.bio) missing.push("bio");
    if (!snapshot.external_urls.length) missing.push("external_urls");
    if (followers.value === null) missing.push("followers");
    if (following.value === null) missing.push("following");
    if (postCount.value === null) missing.push("post_count");
    snapshot.missing_fields = missing;
    return snapshot;
  }

  /** The request body sent to the backend (PRD §11 capture payload). */
  function buildLeadPayload(handle, options) {
    const payload = { username: handle, source: "extension" };
    const opts = options || {};
    if (opts.requestId) payload.request_id = opts.requestId;
    if (opts.snapshot) payload.profile_snapshot = opts.snapshot;
    return payload;
  }

  /** A stable client-generated request id per creator (retries reuse it). */
  function makeRequestId(cryptoObj) {
    const source = cryptoObj || (typeof crypto !== "undefined" ? crypto : null);
    if (source && typeof source.randomUUID === "function") return source.randomUUID();
    return "req-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  /** Map an HTTP status + parsed body to a clear UI state. */
  function classifyResponse(status, body) {
    const leadId = body && body.lead ? body.lead.lead_id : undefined;
    if (status === 201) {
      return { state: "created", message: "Added to the pipeline.", leadId };
    }
    if (status === 200) {
      const outcome = body && body.outcome;
      if (outcome === "updated") {
        return { state: "updated", message: "Profile updated.", leadId };
      }
      return { state: "duplicate", message: "Already in the pipeline.", leadId };
    }
    if (status === 401 || status === 403) {
      return { state: "auth", message: "Invalid or missing API key." };
    }
    if (status === 409) {
      return { state: "error", message: "Backend rejected the request." };
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
   * Submit a handle/profile URL (with an optional snapshot) to the backend.
   * `fetchImpl` is injectable for tests.
   */
  async function submitLead({ apiBaseUrl, apiKey, username, requestId, snapshot, fetchImpl }) {
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
        body: JSON.stringify(buildLeadPayload(handle, { requestId, snapshot })),
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

  /**
   * Submit a batch of accounts one-by-one (no bulk endpoint exists).
   * `submit(account)` is injected. Duplicate handles are skipped; partial
   * failures are counted without stopping the run. Returns accurate counts.
   */
  async function runBulkSubmit({ accounts, submit, onProgress }) {
    const summary = { added: 0, existing: 0, skipped: 0, failed: 0, total: 0, results: [] };
    const seen = new Set();

    for (const account of accounts || []) {
      summary.total += 1;
      const handle = extractHandle(account && account.username);
      if (!handle || seen.has(handle.toLowerCase())) {
        summary.skipped += 1;
        summary.results.push({ username: handle || "", state: "skipped" });
        if (typeof onProgress === "function") onProgress(summary);
        continue;
      }
      seen.add(handle.toLowerCase());

      let result;
      try {
        result = await submit({ ...account, username: handle });
      } catch (error) {
        result = { state: "error", message: String(error && error.message ? error.message : error) };
      }

      const state = (result && result.state) || "error";
      if (state === "created") summary.added += 1;
      else if (state === "duplicate" || state === "updated") summary.existing += 1;
      else if (state === "invalid" || state === "config") summary.skipped += 1;
      else summary.failed += 1;

      summary.results.push({
        username: handle,
        state,
        message: result && result.message,
        leadId: result && result.leadId,
      });
      if (typeof onProgress === "function") onProgress(summary);
    }
    return summary;
  }

  return {
    DEFAULT_API_BASE,
    PARSER_VERSION,
    BLOCKED_SEGMENTS,
    CARD_MIN_WIDTH,
    CARD_MAX_WIDTH,
    CARD_MIN_HEIGHT,
    associateSuggestedAccounts,
    buildLeadPayload,
    buildSnapshot,
    classifyResponse,
    cleanExternalUrl,
    extractHandle,
    filterBioLines,
    isStatLine,
    isStatString,
    isVerifiedMarkup,
    isVerifiedText,
    makeRequestId,
    normalizeApiBase,
    normalizeExternalUrls,
    parseCompactCount,
    parseProfileHtml,
    pickDisplayName,
    runBulkSubmit,
    submitLead,
  };
});
