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
