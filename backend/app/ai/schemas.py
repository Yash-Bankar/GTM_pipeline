"""Structured schemas the model must return (validated by Pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    score: int = Field(default=0, ge=0, le=100)


class DossierDraft(BaseModel):
    """Model output for a creator dossier."""

    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    audience: str = ""
    evidenceUrls: list[str] = Field(default_factory=list)
    criterionScores: list[CriterionScore] = Field(default_factory=list)
    uncertainty: str = ""

    def score_map(self) -> dict[str, int]:
        return {item.name: item.score for item in self.criterionScores}


class OutreachDraft(BaseModel):
    """Model output for personalized outreach drafts."""

    model_config = ConfigDict(extra="ignore")

    emailSubject: str = ""
    emailBody: str = ""
    dmBody: str = ""
