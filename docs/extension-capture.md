# Extension capture feasibility (T03)

Feasibility notes for capturing an open Instagram profile from the browser
extension, plus the "Add All Verified" discovery. This documents what is
extractable, how reliable it is, how missing fields are handled, and the
platform constraints. It is a **feasibility record**, not a claim of live
verification — see "Verification status" at the end.

## What the extension reads (profile page)

| Field | Source in the open DOM | Reliability |
| --- | --- | --- |
| Username | URL path segment (validated) | High — required |
| Display name | `document.title` / `og:title` `Name (@handle)`, else heading/span in `header`, filtered by `pickDisplayName` (drops counts like "2,118" and stat words) | Medium |
| Verified | `<header>` `[aria-label]`/`[title]` containing "verified", else badge `<svg>` markup | Medium — heuristic |
| Bio | `header` → anchors/buttons/counts stripped, then `span[dir="auto"]` lines, via `parseProfileHtml` + `filterBioLines` | Medium |
| External URLs | `header` `a[href]` (unwrapped from `l.instagram.com/?u=…`, trackers stripped); Threads canonicalized to `https://www.threads.net/@handle`; "and N more" buttons ignored | Medium |
| Followers / following / posts | `N followers|following|posts` in header + meta description | Medium — locale dependent |
| Source URL | Canonical `https://www.instagram.com/<handle>/` | High |
| Captured at / parser version | Client clock / constant | High |

Nothing outside the profile header is read for the snapshot. Media, follower
lists, private content, cookies and session tokens are never collected.

## Count parsing and precision

`parseCompactCount` returns `{ value, display, precision }`:

- `"1,234"` → `{ value: 1234, precision: "exact" }`
- `"12.3K"` → `{ value: 12300, precision: "approximate" }`
- `"1.2M"` / `"3B"` → approximate with the corresponding magnitude
- Anything else (e.g. `"—"`, empty, an unsupported locale grouping) → `{ value: null, precision: "unknown" }`

Missing or unsupported values stay `null` and are **never** converted to zero
(PRD §5.1). The original display text is preserved alongside the value.

## Missing-field behavior

`buildSnapshot` emits an explicit `missing_fields` list (also recomputed
server-side): `display_name`, `bio`, `external_urls`, `followers`, `following`,
`post_count`. The popup shows each missing field as `unknown`, and the backend
returns the effective list in the capture response so the dashboard can prompt a
recapture.

## Verified discovery ("Add All Verified")

Ported from the previous extension's proven approach, scoped to what it reliably
handled — the profile page's **"Suggested for you"** rail:

1. Find the element whose trimmed text is exactly `suggested for you`, walk up to
   a container with ≥2 "Follow" texts (height ≥160, width ≥300).
2. For each `Dismiss` button, walk up ≤10 ancestors to a card of width 120–260,
   height ≥160, containing `Follow` and ≥1 profile link.
3. A card is verified if any `[aria-label]`/`[title]` contains "verified" **or**
   any badge `<svg>` markup contains "verified".
4. Accounts are deduplicated by normalized username.

The DOM is reduced to plain descriptors; the geometry/association/dedup logic
lives in `lib.js` and is unit-tested without a browser.

### Not handled

Explore/Search grids, the Followers/Following modals, Reels, and other layouts
the old implementation did not reliably handle. On those pages the popup reports
that the rail is unsupported rather than guessing.

## Platform constraints

- Instagram is a client-rendered SPA; the rail only exists after navigation and
  virtualization may unmount off-screen cards. Only **currently rendered** cards
  are discovered (same as the old extension).
- Class names are obfuscated and change frequently, so detection relies on
  `aria-label`/`title` text, badge svg markup, and geometry — all heuristic.
- No automatic HikerAPI call is made when snapshot data is missing. A new lead
  still enqueues the existing `profile_fetch` job (unchanged pipeline behavior);
  gating that behind an explicit provider choice is T06, out of scope here.

## Verification status

- Deterministic unit tests cover parsing, URL cleaning, verified association,
  deduplication, batch counts, and request-id reuse (`node --test extension/`).
- Backend contract tests cover the capture payload, bounds, idempotency, and
  non-erasure (`tests/test_api_leads.py`).
- **No live Chrome run was performed in this environment.** The selectors are
  ported from the previous extension and exercised against synthetic fixtures
  only. Validate on a real profile page (see the extension README checklist)
  before claiming live extraction works.
