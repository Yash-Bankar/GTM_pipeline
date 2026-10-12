"""AI service: turns evidence into a validated dossier and outreach drafts."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.ai import AIProvider

from .evidence import Evidence
from .prompts import (
    DOSSIER_SYSTEM,
    OUTREACH_SYSTEM,
    build_dossier_prompt,
    build_outreach_prompt,
)
from .rubric import DEFAULT_RUBRIC, Rubric, compute_qualification
from .schemas import DossierDraft, OutreachDraft


@dataclass
class DossierResult:
    summary: str
    topics: list[str] = field(default_factory=list)
    audience: str = ""
    evidence_urls: list[str] = field(default_factory=list)
    score: int = 0
    tier: str = "D"
    criterion_scores: dict[str, int] = field(default_factory=dict)
    uncertainty: str = ""


class AIService:
    def __init__(self, provider: AIProvider, rubric: Rubric = DEFAULT_RUBRIC) -> None:
        self._provider = provider
        self._rubric = rubric

    @property
    def rubric(self) -> Rubric:
        return self._rubric

    def generate_dossier(self, evidence: Evidence) -> DossierResult:
        prompt = build_dossier_prompt(evidence, self._rubric)
        draft: DossierDraft = self._provider.generate_structured(
            prompt=prompt, system=DOSSIER_SYSTEM, schema=DossierDraft
        )
        scores = draft.score_map()
        score, tier = compute_qualification(scores, self._rubric)
        urls = [url for url in draft.evidenceUrls if url] or evidence.source_urls()
        return DossierResult(
            summary=draft.summary.strip(),
            topics=[topic.strip() for topic in draft.topics if topic.strip()],
            audience=draft.audience.strip(),
            evidence_urls=urls,
            score=score,
            tier=tier,
            criterion_scores=scores,
            uncertainty=draft.uncertainty.strip(),
        )

    def generate_outreach(self, evidence: Evidence, dossier_summary: str) -> OutreachDraft:
        prompt = build_outreach_prompt(evidence, dossier_summary, self._rubric)
        return self._provider.generate_structured(
            prompt=prompt, system=OUTREACH_SYSTEM, schema=OutreachDraft
        )
