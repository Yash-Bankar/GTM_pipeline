# Gemini + AI Outputs (Phase 6)

Server-side AI generation for dossiers and outreach drafts. Provider abstraction
in `backend/app/providers/ai.py`; rubric/prompts/service in `backend/app/ai/`.
Credentials stay server-side and are never logged.

## Provider abstraction

```python
class AIProvider(ABC):
    def generate_structured(self, *, prompt, system, schema) -> BaseModel: ...
```

- `GeminiProvider` — official `google-genai` SDK, structured output via
  `response_schema`, retries on 429/5xx/timeout, typed errors.
- Tests use a fake provider, so the pipeline is provider-agnostic.

Typed errors: `AIConfigError` (no key/model, 401/403), `AIRateLimitError` (429
after retries), `AIModelError` (400/404/other), `AIResponseError` (non-JSON or
schema-validation failure), `AINetworkError` (transport).

## Configuration

```text
GEMINI_API_KEY=            # required for AI stages
GEMINI_MODEL=gemini-3.8-flash
AI_ENABLED=true            # set false to disable AI stages entirely
AI_TEMPERATURE=0.4
AI_MAX_OUTPUT_TOKENS=2048
AI_TIMEOUT_SECONDS=60
AI_MAX_ATTEMPTS=3
AI_RUBRIC_JSON=            # optional rubric override (JSON)
AI_MAX_POSTS_EVIDENCE=10
AI_MAX_PAGES_EVIDENCE=5
AI_EVIDENCE_TEXT_CHARS=1500
```

**Usage control:**

- `AI_ENABLED=false` (or a missing `GEMINI_API_KEY`) means the worker registers
  no AI stages and `profile_fetch` does not enqueue them.
- `AI_MAX_OUTPUT_TOKENS` caps response size; `AI_MAX_ATTEMPTS` bounds retries.
- `AI_MAX_POSTS_EVIDENCE` / `AI_MAX_PAGES_EVIDENCE` / `AI_EVIDENCE_TEXT_CHARS`
  bound how much scraped text is sent, controlling token cost.
- Generation is **idempotent**: an existing dossier/outreach in `NEEDS_REVIEW`
  is not regenerated, so re-running jobs does not re-spend tokens.
- `GEMINI_MODEL` selects the model; a wrong model surfaces as `AIModelError`
  (HTTP 404).

## Outputs (Google Sheets, keyed by `leadId`)

### `Dossiers`

```text
leadId, username, usernameNormalized, summary, topics, audience, evidenceUrls,
qualificationScore, qualificationTier, rubric, criterionScores, uncertainty,
model, status, lastError, generatedAt, createdAt, updatedAt
```

- `status`: `NEEDS_REVIEW` | `insufficient_evidence` | `error`.
- `qualificationScore` (0-100) + `qualificationTier` (A/B/C/D) are computed
  deterministically from per-criterion scores and the rubric weights.
- `evidenceUrls` are the source URLs the model cited (falling back to the
  lead's known URLs). `uncertainty` records what could not be supported.

### `Outreach`

`subject`/`body` = email draft; `dmBody` = DM draft. `channel="email+dm"`,
`status="NEEDS_REVIEW"`. **Nothing is sent** — drafts only.

## Rubric

Default criteria (weights): `finance_relevance` 0.30, `audience_fit` 0.20,
`contactability` 0.20, `activity` 0.15, `brand_safety` 0.15. The model returns a
0-100 score per criterion; the code computes the weighted total and tier
(`>=80 A`, `>=60 B`, `>=40 C`, else `D`). Override with `AI_RUBRIC_JSON`:

```json
{"name":"custom","version":"1","criteria":[{"name":"fit","weight":1,"description":"..."}]}
```

## Safety

- **Scraped text is untrusted.** Bios, captions and page text are wrapped in
  `<untrusted_*>` delimiters; the system instruction forbids following any
  instructions inside them (prompt-injection resistance).
- **No invented facts.** The model must only state evidence-backed facts; if the
  evidence does not support a claim (e.g. audience composition) it must omit it
  and record the gap in `uncertainty`.
- **Human review required.** All outputs are `NEEDS_REVIEW`; there is no sending.
- **Missing evidence** → the dossier is marked `insufficient_evidence` and no AI
  call is made; the outreach stage skips.

## Pipeline

`profile_fetch` enqueues `ai_dossier` (low priority, so media/website evidence
runs first); `ai_dossier` enqueues `ai_outreach` on success. Both are idempotent
and optional.

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_gemini_provider.py tests\test_ai_service.py tests\test_worker_ai_stages.py
```

Manual connectivity check (one tiny structured request; key never printed):

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_gemini.py
```

If it returns `AIModelError ... 404`, the configured `GEMINI_MODEL` is not
available to your key — list what you can use and update `.env`:

```powershell
.\backend\.venv\Scripts\python.exe -c "from app.config import get_settings; from google import genai; c=genai.Client(api_key=get_settings().gemini_api_key); print('\n'.join(m.name for m in c.models.list()))"
```

Coverage: parsed/text-JSON success, malformed JSON, schema-validation failure,
empty response, 429 retry-then-success, 429 exhaustion, 400 model error, missing
config, rubric scoring/tiers, untrusted wrapping, missing evidence, duplicate
generation, and outreach skip/dedup.
