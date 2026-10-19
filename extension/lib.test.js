/**
 * Node tests for the extension's shared helpers.
 * Run from the repository root:  node --test extension/
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const SynpoLib = require("./lib.js");

function mockFetch(responses) {
  const calls = [];
  let index = 0;
  const impl = async (url, init) => {
    calls.push({ url, init });
    const response = responses[Math.min(index, responses.length - 1)];
    index += 1;
    if (response.throw) throw new Error("network down");
    return { status: response.status, json: async () => response.body };
  };
  impl.calls = calls;
  return impl;
}

test("extractHandle parses profile URLs and handles", () => {
  assert.equal(SynpoLib.extractHandle("https://www.instagram.com/natgeo/"), "natgeo");
  assert.equal(SynpoLib.extractHandle("https://instagram.com/foo?hl=en"), "foo");
  assert.equal(SynpoLib.extractHandle("@bar"), "bar");
  assert.equal(SynpoLib.extractHandle("/baz/"), "baz");
});

test("extractHandle rejects non-profile and non-instagram URLs", () => {
  assert.equal(SynpoLib.extractHandle("https://www.instagram.com/p/ABC123/"), "");
  assert.equal(SynpoLib.extractHandle("https://www.instagram.com/explore/"), "");
  assert.equal(SynpoLib.extractHandle("https://www.instagram.com/reels/"), "");
  assert.equal(SynpoLib.extractHandle("https://example.com/foo"), "");
  assert.equal(SynpoLib.extractHandle(""), "");
});

test("classifyResponse maps statuses to clear states", () => {
  assert.equal(SynpoLib.classifyResponse(201, { lead: { lead_id: "ld_1" } }).state, "created");
  assert.equal(SynpoLib.classifyResponse(201, { lead: { lead_id: "ld_1" } }).leadId, "ld_1");
  assert.equal(SynpoLib.classifyResponse(200, {}).state, "duplicate");
  assert.equal(SynpoLib.classifyResponse(401, {}).state, "auth");
  assert.equal(SynpoLib.classifyResponse(403, {}).state, "auth");
  assert.equal(SynpoLib.classifyResponse(422, { detail: [{ msg: "bad url" }] }).state, "invalid");
  assert.equal(SynpoLib.classifyResponse(500, {}).state, "error");
});

test("submitLead: repeated clicks yield created then duplicate", async () => {
  const fetchImpl = mockFetch([
    { status: 201, body: { created: true, lead: { lead_id: "ld_1" } } },
    { status: 200, body: { created: false, lead: { lead_id: "ld_1" } } },
  ]);
  const args = { apiBaseUrl: "http://127.0.0.1:8000", apiKey: "", username: "natgeo", fetchImpl };

  assert.equal((await SynpoLib.submitLead(args)).state, "created");
  assert.equal((await SynpoLib.submitLead(args)).state, "duplicate");
  assert.equal(fetchImpl.calls.length, 2);
  assert.equal(fetchImpl.calls[0].url, "http://127.0.0.1:8000/api/v1/leads");
});

test("submitLead: network failure returns a retryable state", async () => {
  const fetchImpl = mockFetch([{ throw: true }]);
  const result = await SynpoLib.submitLead({ username: "natgeo", fetchImpl });
  assert.equal(result.state, "network");
});

test("submitLead: invalid profile URL is rejected before any request", async () => {
  const fetchImpl = mockFetch([{ status: 201, body: {} }]);
  const result = await SynpoLib.submitLead({ username: "https://example.com/x", fetchImpl });
  assert.equal(result.state, "invalid");
  assert.equal(fetchImpl.calls.length, 0);
});

test("submitLead: authentication failure is surfaced", async () => {
  const fetchImpl = mockFetch([{ status: 401, body: { detail: "Invalid or missing API key." } }]);
  const result = await SynpoLib.submitLead({ username: "natgeo", fetchImpl });
  assert.equal(result.state, "auth");
});

test("submitLead: sends the x-api-key header when configured", async () => {
  const fetchImpl = mockFetch([{ status: 201, body: { lead: { lead_id: "ld_2" } } }]);
  await SynpoLib.submitLead({ apiKey: "s3cret", username: "natgeo", fetchImpl });
  assert.equal(fetchImpl.calls[0].init.headers["x-api-key"], "s3cret");
});

test("submitLead: missing API base returns a config state", async () => {
  const result = await SynpoLib.submitLead({ apiBaseUrl: "   ", username: "natgeo" });
  assert.equal(result.state, "config");
});

test("parseCompactCount keeps precision and never fabricates zero", () => {
  assert.deepEqual(SynpoLib.parseCompactCount("1,234"), {
    value: 1234,
    display: "1,234",
    precision: "exact",
  });
  assert.deepEqual(SynpoLib.parseCompactCount("12.3K"), {
    value: 12300,
    display: "12.3K",
    precision: "approximate",
  });
  assert.equal(SynpoLib.parseCompactCount("1.2M").value, 1200000);
  assert.equal(SynpoLib.parseCompactCount("3B").value, 3000000000);
  const unknown = SynpoLib.parseCompactCount("—");
  assert.equal(unknown.value, null);
  assert.equal(unknown.precision, "unknown");
  assert.equal(SynpoLib.parseCompactCount("").precision, "unknown");
});

test("cleanExternalUrl unwraps redirects, drops trackers and social hosts", () => {
  assert.equal(
    SynpoLib.cleanExternalUrl("https://example.com/x?utm_source=ig&utm_medium=bio"),
    "https://example.com/x",
  );
  assert.equal(
    SynpoLib.cleanExternalUrl("https://l.instagram.com/?u=https%3A%2F%2Freal.example%2Fp"),
    "https://real.example/p",
  );
  assert.equal(SynpoLib.cleanExternalUrl("https://www.instagram.com/someone/"), "");
  assert.equal(SynpoLib.cleanExternalUrl("https://facebook.com/page"), "");
  assert.equal(
    SynpoLib.cleanExternalUrl("https://www.threads.com/@someone?xmt=abc"),
    "https://www.threads.net/@someone",
  );
  assert.equal(SynpoLib.cleanExternalUrl("javascript:alert(1)"), "");
  assert.equal(SynpoLib.cleanExternalUrl("not a url"), "");
});

test("cleanExternalUrl canonicalizes Threads links from every host form", () => {
  assert.equal(
    SynpoLib.cleanExternalUrl("https://www.threads.net/@mkbhd?xmt=xyz"),
    "https://www.threads.net/@mkbhd",
  );
  assert.equal(SynpoLib.cleanExternalUrl("https://threads.com/mkbhd"), "https://www.threads.net/@mkbhd");
  assert.equal(
    SynpoLib.cleanExternalUrl("https://l.instagram.com/?u=https%3A%2F%2Fwww.threads.net%2F%40mkbhd"),
    "https://www.threads.net/@mkbhd",
  );
  assert.equal(SynpoLib.cleanExternalUrl("https://www.threads.net/t/ABC123"), "");
});

test("cleanExternalUrl strips igshid and xmt tracking params", () => {
  assert.equal(
    SynpoLib.cleanExternalUrl("https://example.com/p?igshid=abc&xmt=1&q=keep"),
    "https://example.com/p?q=keep",
  );
});

test("filterBioLines drops injected UI and keeps the real bio", () => {
  const lines = [
    "caseyneistat", // username
    "Casey Neistat", // display name
    "youtube", // real bio link label
    "Add to GTM", // injected extension button
    "Suggested for you", // rail heading
    "See all",
    "Followed by mundarishi, haram_khor_ + 5 more", // follower overlay
    "2,031 posts", // counts
    "1.", // stray overlay artifact
    "youtube", // duplicate
    "Film director & storyteller",
  ];
  const bio = SynpoLib.filterBioLines(lines, {
    username: "caseyneistat",
    displayName: "Casey Neistat",
  });
  assert.deepEqual(bio, ["youtube", "Film director & storyteller"]);
});

test("filterBioLines drops a single polluted suggestion line", () => {
  const bio = SynpoLib.filterBioLines(
    ["Suggested for you See all mrbeast MrBeast joerogan Joe Rogan"],
    { username: "x", displayName: "X" },
  );
  assert.deepEqual(bio, []);
});

test("filterBioLines drops liked-by and follower-detail overlays", () => {
  const bio = SynpoLib.filterBioLines(
    ["Liked by jane and 12 others", "Followed by a, b + 3 more", "Founder & investor"],
    {},
  );
  assert.deepEqual(bio, ["Founder & investor"]);
});

test("filterBioLines compares the handle with or without a leading @", () => {
  const bio = SynpoLib.filterBioLines(["@caseyneistat", "hello"], { username: "caseyneistat" });
  assert.deepEqual(bio, ["hello"]);
});

test("isStatLine flags counts and stats but not bio text", () => {
  assert.equal(SynpoLib.isStatLine("2,118"), true);
  assert.equal(SynpoLib.isStatLine("522"), true);
  assert.equal(SynpoLib.isStatLine("2.7M"), true);
  assert.equal(SynpoLib.isStatLine("19.5M followers"), true);
  assert.equal(SynpoLib.isStatLine("Reel creator"), false);
  assert.equal(SynpoLib.isStatLine("I promise I won't overdo the filters."), false);
});

test("pickDisplayName skips counts, stat words and the handle", () => {
  assert.equal(
    SynpoLib.pickDisplayName(["522", "65", "2,118", "posts", "followers", "mrbeast", "MrBeast"], {
      username: "mrbeast",
    }),
    "MrBeast",
  );
  assert.equal(SynpoLib.pickDisplayName(["2.7M followers", "Marques Brownlee"], {}), "Marques Brownlee");
  assert.equal(SynpoLib.pickDisplayName(["2,118"], {}), "");
  assert.equal(SynpoLib.pickDisplayName([], {}), "");
});

test("filterBioLines strips leading stat lines and keeps category badges", () => {
  const bio = SynpoLib.filterBioLines(["2,118", "442M followers", "Video creator", "SUBSCRIBE"], {});
  assert.deepEqual(bio, ["Video creator", "SUBSCRIBE"]);
});

test("filterBioLines drops 'and N more' link buttons", () => {
  const bio = SynpoLib.filterBioLines(["and 2 more", "3 more", "Reel creator"], {});
  assert.deepEqual(bio, ["Reel creator"]);
});

test("parseProfileHtml extracts name, bio and links (mkbhd fixture)", () => {
  const html = `
    <header>
      <section>
        <div><h2>mkbhd</h2></div>
        <div><span dir="auto">Marques Brownlee</span></div>
        <ul><li><span>1,234 posts</span></li><li><span>19.5M followers</span></li></ul>
        <div><span dir="auto">I promise I won't overdo the filters.</span></div>
        <a href="https://l.instagram.com/?u=https%3A%2F%2Fmkbhd.com%2F&amp;e=xyz">mkbhd.com</a>
        <a href="https://www.threads.net/@mkbhd?xmt=abc"><span dir="auto">@mkbhd</span></a>
        <button>Follow</button>
        <button>Add to GTM</button>
        <div>Suggested for you</div>
      </section>
    </header>`;
  const parsed = SynpoLib.parseProfileHtml(html, { username: "mkbhd" });
  assert.equal(parsed.displayName, "Marques Brownlee");
  assert.equal(parsed.bio, "I promise I won't overdo the filters.");
  assert.ok(parsed.externalUrls.includes("https://mkbhd.com/"));
  assert.ok(parsed.externalUrls.includes("https://www.threads.net/@mkbhd"));
});

test("parseProfileHtml parses the MrBeast header (stats never become the name)", () => {
  const html = `
    <header><section>
      <div><h2>mrbeast</h2></div>
      <div><span dir="auto">MrBeast</span></div>
      <ul><li>2,118 posts</li><li>442M followers</li><li>1,234 following</li></ul>
      <div><span dir="auto">2,118</span></div>
      <div><span dir="auto">Video creator</span></div>
      <div><span dir="auto">SUBSCRIBE</span></div>
      <a href="https://l.instagram.com/?u=https%3A%2F%2Fwww.youtube.com%2F%40MrBeast&amp;e=x">youtube.com/@MrBeast</a>
      <button>and 2 more</button>
    </section></header>`;
  const parsed = SynpoLib.parseProfileHtml(html, { username: "mrbeast" });
  assert.equal(parsed.displayName, "MrBeast");
  assert.deepEqual(parsed.bioLines, ["Video creator", "SUBSCRIBE"]);
  assert.ok(parsed.externalUrls.includes("https://www.youtube.com/@MrBeast"));
});

test("parseProfileHtml parses the IShowSpeed header (redirect unwrap + Threads)", () => {
  const html = `
    <header><section>
      <div><h1>ishowspeed</h1></div>
      <div><span dir="auto">IShowSpeed</span></div>
      <ul><li>65 posts</li><li>33.8M followers</li></ul>
      <div><span dir="auto">Reel creator</span></div>
      <div><span dir="auto">World's fastest</span></div>
      <a href="https://l.instagram.com/?u=https%3A%2F%2Fyoutu.be%2FRE3_PGwDwhw&amp;e=x">youtu.be/RE3_PGwDwhw</a>
      <a href="https://www.threads.net/@ishowspeed"><span dir="auto">@ishowspeed</span></a>
      <button>and 3 more</button>
    </section></header>`;
  const parsed = SynpoLib.parseProfileHtml(html, { username: "ishowspeed" });
  assert.equal(parsed.displayName, "IShowSpeed");
  assert.deepEqual(parsed.bioLines, ["Reel creator", "World's fastest"]);
  assert.ok(parsed.externalUrls.includes("https://youtu.be/RE3_PGwDwhw"));
  assert.ok(parsed.externalUrls.includes("https://www.threads.net/@ishowspeed"));
});

test("parseProfileHtml never leaks injected buttons or the Suggested rail", () => {
  const html = `
    <header><section>
      <div><span dir="auto">Casey Neistat</span></div>
      <div><span dir="auto">youtube</span></div>
      <button>Add to GTM</button>
      <div>Suggested for you</div>
      <div><span dir="auto">See all</span></div>
      <a href="/mrbeast/"><span dir="auto">mrbeast</span></a>
      <div><span dir="auto">Followed by a, b + 5 more</span></div>
    </section></header>`;
  const parsed = SynpoLib.parseProfileHtml(html, { username: "caseyneistat" });
  assert.equal(parsed.displayName, "Casey Neistat");
  assert.equal(parsed.bio, "youtube");
  assert.ok(!parsed.bio.includes("Add to GTM"));
  assert.ok(!parsed.bio.includes("Suggested for you"));
  assert.ok(!parsed.bio.includes("See all"));
  assert.ok(!parsed.bio.includes("Followed by"));
  assert.ok(!parsed.bio.includes("mrbeast")); // suggestion card is an anchor
});

test("parseProfileHtml returns visible bio text instead of unknown", () => {
  const html =
    '<header><section><div><span dir="auto">Marques Brownlee</span></div>' +
    '<div><span dir="auto">I promise I won\'t overdo the filters.</span></div></section></header>';
  const parsed = SynpoLib.parseProfileHtml(html, { username: "mkbhd" });
  assert.equal(parsed.displayName, "Marques Brownlee");
  assert.equal(parsed.bio, "I promise I won't overdo the filters.");
  assert.equal(parsed.bioLines.length, 1);
});

test("parseProfileHtml leaves bio empty for a link-only bio but keeps the links", () => {
  const html = `
    <header><section>
      <div><span dir="auto">Casey Neistat</span></div>
      <a href="https://l.instagram.com/?u=https%3A%2F%2Fwww.youtube.com%2Fuser%2Fcaseyneistat">youtube</a>
      <a href="https://www.threads.com/@caseyneistat?xmt=abc"><span dir="auto">@caseyneistat</span></a>
      <button>Add to GTM</button>
    </section></header>`;
  const parsed = SynpoLib.parseProfileHtml(html, { username: "caseyneistat" });
  assert.equal(parsed.bio, "");
  assert.ok(parsed.externalUrls.includes("https://www.youtube.com/user/caseyneistat"));
  assert.ok(parsed.externalUrls.includes("https://www.threads.net/@caseyneistat"));
});

test("parseProfileHtml builds a full snapshot-ready bio with line breaks", () => {
  const html =
    '<header><section><div><span dir="auto">Marques Brownlee</span></div>' +
    '<div><span dir="auto">Line one<br>Line two</span></div></section></header>';
  const parsed = SynpoLib.parseProfileHtml(html, { username: "x" });
  assert.deepEqual(parsed.bioLines, ["Line one", "Line two"]);
  assert.equal(parsed.bio, "Line one\nLine two");
});

test("normalizeExternalUrls dedupes and caps at 10", () => {
  const urls = ["https://a.example/", "https://a.example", ...Array.from({ length: 12 }, (_, i) => `https://s${i}.example/`)];
  const cleaned = SynpoLib.normalizeExternalUrls(urls);
  assert.equal(cleaned.length, 10);
  assert.equal(cleaned.filter((u) => u.startsWith("https://a.example")).length, 1);
});

test("buildSnapshot marks missing fields and keeps unknown counts null", () => {
  const snapshot = SynpoLib.buildSnapshot(
    {
      displayName: "",
      isVerified: true,
      bioLines: ["Finance educator.", "Books below."],
      externalUrls: ["https://example.com"],
      followersText: "12.3K",
      followingText: "",
      postsText: "—",
    },
    { sourceUrl: "https://www.instagram.com/x/", capturedAt: "2026-10-19T00:00:00Z" },
  );
  assert.equal(snapshot.is_verified, true);
  assert.equal(snapshot.bio, "Finance educator.\nBooks below.");
  assert.equal(snapshot.followers.value, 12300);
  assert.equal(snapshot.following.value, null);
  assert.equal(snapshot.post_count.value, null);
  assert.deepEqual(snapshot.missing_fields, ["display_name", "following", "post_count"]);
  assert.equal(snapshot.parser_version, SynpoLib.PARSER_VERSION);
});

test("buildSnapshot caps bio length", () => {
  const snapshot = SynpoLib.buildSnapshot({ bioLines: ["x".repeat(5000)] }, {});
  assert.equal(snapshot.bio.length, 2200);
});

test("associateSuggestedAccounts keeps verified cards and dedupes", () => {
  const base = { text: "creator Follow", width: 180, height: 200, hasFollow: true, linkCount: 1 };
  const descriptors = [
    { ...base, username: "verified.one", fullName: "Verified One", labels: ["Verified"], svgMarkup: [] },
    { ...base, username: "Verified.One", fullName: "Dup", labels: ["Verified"], svgMarkup: [] },
    { ...base, username: "plain.two", fullName: "Plain Two", labels: [], svgMarkup: ["<svg></svg>"] },
    { ...base, username: "svg.verified", fullName: "Svg", labels: [], svgMarkup: ['<svg aria-label="Verified badge"></svg>'] },
  ];
  const accounts = SynpoLib.associateSuggestedAccounts(descriptors);
  assert.deepEqual(accounts.map((a) => a.username), ["verified.one", "plain.two", "svg.verified"]);
  assert.deepEqual(accounts.map((a) => a.verified), [true, false, true]);
});

test("associateSuggestedAccounts ignores non-card geometry and non-profiles", () => {
  const accounts = SynpoLib.associateSuggestedAccounts([
    { username: "wide.card", width: 500, height: 200, hasFollow: true, linkCount: 1 },
    { username: "short.card", width: 180, height: 40, hasFollow: true, linkCount: 1 },
    { username: "no.follow", width: 180, height: 200, hasFollow: false, linkCount: 1 },
    { username: "no.link", width: 180, height: 200, hasFollow: true, linkCount: 0 },
    { username: "p", width: 180, height: 200, hasFollow: true, linkCount: 1 },
    null,
  ]);
  assert.deepEqual(accounts, []);
});

test("buildLeadPayload nests request_id and snapshot; handle-only omits them", () => {
  const handleOnly = SynpoLib.buildLeadPayload("natgeo");
  assert.deepEqual(handleOnly, { username: "natgeo", source: "extension" });

  const withCapture = SynpoLib.buildLeadPayload("natgeo", {
    requestId: "req-1",
    snapshot: { display_name: "Nat Geo" },
  });
  assert.equal(withCapture.request_id, "req-1");
  assert.equal(withCapture.profile_snapshot.display_name, "Nat Geo");
});

test("makeRequestId prefers crypto.randomUUID", () => {
  const fakeCrypto = { randomUUID: () => "uuid-123" };
  assert.equal(SynpoLib.makeRequestId(fakeCrypto), "uuid-123");
  assert.match(SynpoLib.makeRequestId({}), /^req-/);
});

test("classifyResponse distinguishes updated from duplicate", () => {
  assert.equal(SynpoLib.classifyResponse(200, { outcome: "updated" }).state, "updated");
  assert.equal(SynpoLib.classifyResponse(200, { outcome: "unchanged" }).state, "duplicate");
  assert.equal(SynpoLib.classifyResponse(200, {}).state, "duplicate");
});

test("submitLead sends request_id and profile_snapshot", async () => {
  const fetchImpl = mockFetch([{ status: 201, body: { created: true, lead: { lead_id: "ld_9" } } }]);
  await SynpoLib.submitLead({
    username: "natgeo",
    requestId: "req-9",
    snapshot: { display_name: "Nat Geo" },
    fetchImpl,
  });
  const body = JSON.parse(fetchImpl.calls[0].init.body);
  assert.equal(body.request_id, "req-9");
  assert.equal(body.profile_snapshot.display_name, "Nat Geo");
});

test("runBulkSubmit reports accurate added/existing/skipped/failed counts", async () => {
  const accounts = [
    { username: "a.one" },
    { username: "A.One" }, // duplicate of a.one
    { username: "b.two" },
    { username: "c.three" },
    { username: "p" }, // blocked segment → skipped
  ];
  const submit = async ({ username }) => {
    if (username === "a.one") return { state: "created", leadId: "ld_1" };
    if (username === "b.two") return { state: "duplicate" };
    return { state: "network", message: "down" };
  };
  const summary = await SynpoLib.runBulkSubmit({ accounts, submit });
  assert.equal(summary.total, 5);
  assert.equal(summary.added, 1);
  assert.equal(summary.existing, 1);
  assert.equal(summary.skipped, 2); // dup handle + blocked segment
  assert.equal(summary.failed, 1);
});

test("runBulkSubmit retry reuses request ids without duplicating successes", async () => {
  const seen = [];
  const submit = async (account) => {
    seen.push(account.requestId);
    return { state: "created" };
  };
  const first = await SynpoLib.runBulkSubmit({
    accounts: [{ username: "a.one", requestId: "req-a" }, { username: "b.two", requestId: "req-b" }],
    submit,
  });
  assert.equal(first.added, 2);
  // Retry of a failed account reuses the original request id (server dedupes).
  await SynpoLib.runBulkSubmit({ accounts: [{ username: "b.two", requestId: "req-b" }], submit });
  assert.deepEqual(seen, ["req-a", "req-b", "req-b"]);
});
