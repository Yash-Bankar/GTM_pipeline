from __future__ import annotations

from app.ai import AIService, DEFAULT_RUBRIC
from app.ai.schemas import CriterionScore, DossierDraft, OutreachDraft
from app.constants import AI_STATUS_ERROR, AI_STATUS_INSUFFICIENT, AI_STATUS_NEEDS_REVIEW
from app.providers.errors import AIRateLimitError, AIResponseError
from app.sheets.models import Dossier, LeadPost, WebsitePage
from app.sheets.schemas import (
    KEY_DOSSIERS,
    KEY_IG_LEADS,
    KEY_OUTREACH,
    KEY_POSTS,
    KEY_WEBSITE_PAGES,
)
from app.worker.pipeline import AIDossierStage, AIOutreachStage
from fakes import FakeAIProvider


def _seed_evidence(store, lead, *, bio="Finance educator."):
    store.lead.update_by_key(KEY_IG_LEADS, lead.lead_id, {"bio": bio})
    store.posts.append_model(
        KEY_POSTS, LeadPost(postId="p1", leadId=lead.lead_id, caption="Investing basics")
    )
    store.website.append_model(
        KEY_WEBSITE_PAGES,
        WebsitePage(pageId="pg1", leadId=lead.lead_id, url="https://x.test", title="About", text="Coaching"),
    )


def _full_score_draft(summary="Finance educator."):
    return DossierDraft(
        summary=summary,
        topics=["investing"],
        criterionScores=[CriterionScore(name=c.name, score=100) for c in DEFAULT_RUBRIC.criteria],
        uncertainty="",
    )


def _dossier_stage(store, provider):
    return AIDossierStage(
        AIService(provider),
        store.lead,
        store.posts,
        store.website,
        store.dossiers,
        model_name="gemini-test",
        job_store=store.jobs,
    )


def _outreach_stage(store, provider):
    return AIOutreachStage(
        AIService(provider),
        store.lead,
        store.posts,
        store.website,
        store.dossiers,
        store.outreach,
        model_name="gemini-test",
    )


def test_dossier_stage_generates_and_enqueues_outreach(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.one")
    _seed_evidence(worker_stores, lead)
    worker_stores.jobs.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(dossier=_full_score_draft())
    outcome = _dossier_stage(worker_stores, provider).run(job)

    assert outcome.ok
    row = worker_stores.dossiers.find_row(KEY_DOSSIERS, lead.lead_id, key_header="leadId")
    assert row.values["status"] == AI_STATUS_NEEDS_REVIEW
    assert row.values["qualificationScore"] == "100"
    assert row.values["qualificationTier"] == "A"
    assert row.values["summary"] == "Finance educator."
    assert worker_stores.jobs.find_job("ai_outreach", lead.lead_id) is not None


def test_dossier_stage_insufficient_evidence_skips_ai(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.empty")
    worker_stores.jobs.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(dossier=_full_score_draft())
    outcome = _dossier_stage(worker_stores, provider).run(job)

    assert outcome.ok
    assert provider.calls == 0
    row = worker_stores.dossiers.find_row(KEY_DOSSIERS, lead.lead_id, key_header="leadId")
    assert row.values["status"] == AI_STATUS_INSUFFICIENT


def test_dossier_stage_malformed_response_is_terminal(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.bad")
    _seed_evidence(worker_stores, lead)
    worker_stores.jobs.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(error=AIResponseError("bad json"))
    outcome = _dossier_stage(worker_stores, provider).run(job)

    assert outcome.ok is False
    assert outcome.retryable is False
    assert worker_stores.dossiers.find_row(KEY_DOSSIERS, lead.lead_id, key_header="leadId").values["status"] == AI_STATUS_ERROR


def test_dossier_stage_rate_limit_is_retryable(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.rate")
    _seed_evidence(worker_stores, lead)
    worker_stores.jobs.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(error=AIRateLimitError("429"))
    outcome = _dossier_stage(worker_stores, provider).run(job)

    assert outcome.ok is False
    assert outcome.retryable is True


def test_dossier_stage_does_not_regenerate(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.dup")
    _seed_evidence(worker_stores, lead)
    worker_stores.jobs.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(dossier=_full_score_draft())
    stage = _dossier_stage(worker_stores, provider)
    stage.run(job)
    stage.run(job)  # duplicate run

    assert provider.calls == 1
    assert len(worker_stores.dossiers.read_rows(KEY_DOSSIERS)) == 1


def test_outreach_stage_generates_needs_review_draft(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.out")
    _seed_evidence(worker_stores, lead)
    worker_stores.dossiers.upsert_model(
        KEY_DOSSIERS,
        Dossier(leadId=lead.lead_id, username=lead.username, status=AI_STATUS_NEEDS_REVIEW, summary="Finance educator."),
    )
    worker_stores.jobs.enqueue("ai_outreach", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(
        outreach=OutreachDraft(emailSubject="Hi", emailBody="Body text", dmBody="DM text")
    )
    outcome = _outreach_stage(worker_stores, provider).run(job)

    assert outcome.ok
    row = worker_stores.outreach.find_row(KEY_OUTREACH, lead.lead_id, key_header="leadId")
    assert row.values["status"] == AI_STATUS_NEEDS_REVIEW
    assert row.values["subject"] == "Hi"
    assert row.values["body"] == "Body text"
    assert row.values["dmBody"] == "DM text"


def test_outreach_stage_skips_without_dossier(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.nodossier")
    worker_stores.jobs.enqueue("ai_outreach", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(outreach=OutreachDraft(emailSubject="x"))
    outcome = _outreach_stage(worker_stores, provider).run(job)

    assert outcome.ok
    assert provider.calls == 0
    assert worker_stores.outreach.read_rows(KEY_OUTREACH) == []


def test_outreach_stage_does_not_regenerate(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ai.outdup")
    _seed_evidence(worker_stores, lead)
    worker_stores.dossiers.upsert_model(
        KEY_DOSSIERS,
        Dossier(leadId=lead.lead_id, username=lead.username, status=AI_STATUS_NEEDS_REVIEW, summary="s"),
    )
    worker_stores.jobs.enqueue("ai_outreach", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    provider = FakeAIProvider(outreach=OutreachDraft(emailSubject="Hi", emailBody="b", dmBody="d"))
    stage = _outreach_stage(worker_stores, provider)
    stage.run(job)
    stage.run(job)

    assert provider.calls == 1
    assert len(worker_stores.outreach.read_rows(KEY_OUTREACH)) == 1
