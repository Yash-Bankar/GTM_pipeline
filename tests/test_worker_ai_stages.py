from __future__ import annotations

from app.ai import AIService, DEFAULT_RUBRIC
from app.ai.schemas import CriterionScore, DossierDraft, OutreachDraft
from app.constants import AI_STATUS_ERROR, AI_STATUS_INSUFFICIENT, AI_STATUS_NEEDS_REVIEW
from app.db.repository import Repository
from app.db.schemas import Dossier, LeadPost, PipelineJob, WebsitePage
from app.providers.errors import AIRateLimitError, AIResponseError
from app.worker.pipeline import AIDossierStage, AIOutreachStage
from fakes import FakeAIProvider


def _seed_evidence(repo: Repository, lead, bio: str = "Finance educator.") -> None:
    repo.update_lead(lead.lead_id, {"bio": bio})
    repo.upsert_post(LeadPost(post_id="p1", lead_id=lead.lead_id, caption="Investing basics"))
    repo.upsert_website_page(
        WebsitePage(page_id="pg1", lead_id=lead.lead_id, url="https://x.test", title="About", text="Coaching")
    )


def _full_score_draft(summary: str = "Finance educator.") -> DossierDraft:
    return DossierDraft(
        summary=summary,
        topics=["investing"],
        criterionScores=[CriterionScore(name=c.name, score=100) for c in DEFAULT_RUBRIC.criteria],
        uncertainty="",
    )


def _dossier_stage(provider) -> AIDossierStage:
    return AIDossierStage(AIService(provider), model_name="gemini-test")


def _outreach_stage(provider) -> AIOutreachStage:
    return AIOutreachStage(AIService(provider), model_name="gemini-test")


def _dossier_job(repo: Repository, name: str):
    lead = repo.create_or_get_lead(name)[1]
    repo.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    return lead, repo.claim_next(worker_id="w1")


def _outreach_job(repo: Repository, name: str):
    lead = repo.create_or_get_lead(name)[1]
    repo.enqueue("ai_outreach", lead.lead_id, lead.username, lead.username_normalized)
    return lead, repo.claim_next(worker_id="w1")


def test_dossier_stage_generates_and_enqueues_outreach(repo: Repository) -> None:
    lead, job = _dossier_job(repo, "ai.one")
    _seed_evidence(repo, lead)
    provider = FakeAIProvider(dossier=_full_score_draft())

    outcome = _dossier_stage(provider).run(job, repo)

    assert outcome.ok
    dossier = repo.get_dossier(lead.lead_id)
    assert dossier.status == AI_STATUS_NEEDS_REVIEW
    assert dossier.qualification_score == 100
    assert dossier.qualification_tier == "A"
    assert dossier.summary == "Finance educator."
    assert repo.find_job("ai_outreach", lead.lead_id) is not None


def test_dossier_stage_insufficient_evidence_skips_ai(repo: Repository) -> None:
    lead, job = _dossier_job(repo, "ai.empty")
    provider = FakeAIProvider(dossier=_full_score_draft())
    outcome = _dossier_stage(provider).run(job, repo)
    assert outcome.ok
    assert provider.calls == 0
    assert repo.get_dossier(lead.lead_id).status == AI_STATUS_INSUFFICIENT


def test_dossier_stage_malformed_response_is_terminal(repo: Repository) -> None:
    lead, job = _dossier_job(repo, "ai.bad")
    _seed_evidence(repo, lead)
    provider = FakeAIProvider(error=AIResponseError("bad json"))
    outcome = _dossier_stage(provider).run(job, repo)
    assert outcome.ok is False
    assert outcome.retryable is False
    assert repo.get_dossier(lead.lead_id).status == AI_STATUS_ERROR


def test_dossier_stage_rate_limit_is_retryable(repo: Repository) -> None:
    lead, job = _dossier_job(repo, "ai.rate")
    _seed_evidence(repo, lead)
    provider = FakeAIProvider(error=AIRateLimitError("429"))
    outcome = _dossier_stage(provider).run(job, repo)
    assert outcome.ok is False
    assert outcome.retryable is True


def test_dossier_stage_does_not_regenerate(repo: Repository) -> None:
    lead, job = _dossier_job(repo, "ai.dup")
    _seed_evidence(repo, lead)
    provider = FakeAIProvider(dossier=_full_score_draft())
    stage = _dossier_stage(provider)
    stage.run(job, repo)
    stage.run(job, repo)
    assert provider.calls == 1
    assert len(repo.list_dossiers()) == 1


def test_dossier_stage_force_regenerates(repo: Repository) -> None:
    lead = repo.create_or_get_lead("ai.force")[1]
    _seed_evidence(repo, lead)
    # Existing dossier that would normally be skipped.
    repo.upsert_dossier(
        Dossier(lead_id=lead.lead_id, username=lead.username, status=AI_STATUS_NEEDS_REVIEW, summary="old")
    )
    forced_job = PipelineJob(
        job_id="job_force",
        stage="ai_dossier",
        lead_id=lead.lead_id,
        username=lead.username,
        username_normalized=lead.username_normalized,
        status="running",
        attempt_count=1,
        max_attempts=3,
        payload='{"force": true}',
    )
    provider = FakeAIProvider(dossier=_full_score_draft(summary="regenerated"))

    outcome = _dossier_stage(provider).run(forced_job, repo)

    assert outcome.ok
    assert provider.calls == 1
    assert repo.get_dossier(lead.lead_id).summary == "regenerated"


def test_outreach_stage_generates_needs_review_draft(repo: Repository) -> None:
    lead, job = _outreach_job(repo, "ai.out")
    _seed_evidence(repo, lead)
    repo.upsert_dossier(
        Dossier(lead_id=lead.lead_id, username=lead.username, status=AI_STATUS_NEEDS_REVIEW, summary="Finance educator.")
    )
    provider = FakeAIProvider(outreach=OutreachDraft(emailSubject="Hi", emailBody="Body text", dmBody="DM text"))

    outcome = _outreach_stage(provider).run(job, repo)

    assert outcome.ok
    entry = repo.get_outreach(lead.lead_id)
    assert entry.status == AI_STATUS_NEEDS_REVIEW
    assert entry.subject == "Hi"
    assert entry.body == "Body text"
    assert entry.dm_body == "DM text"


def test_outreach_stage_skips_without_dossier(repo: Repository) -> None:
    _lead, job = _outreach_job(repo, "ai.nodossier")
    provider = FakeAIProvider(outreach=OutreachDraft(emailSubject="x"))
    outcome = _outreach_stage(provider).run(job, repo)
    assert outcome.ok
    assert provider.calls == 0
    assert repo.list_outreach() == []


def test_outreach_stage_does_not_regenerate(repo: Repository) -> None:
    lead, job = _outreach_job(repo, "ai.outdup")
    _seed_evidence(repo, lead)
    repo.upsert_dossier(
        Dossier(lead_id=lead.lead_id, username=lead.username, status=AI_STATUS_NEEDS_REVIEW, summary="s")
    )
    provider = FakeAIProvider(outreach=OutreachDraft(emailSubject="Hi", emailBody="b", dmBody="d"))
    stage = _outreach_stage(provider)
    stage.run(job, repo)
    stage.run(job, repo)
    assert provider.calls == 1
    assert len(repo.list_outreach()) == 1
