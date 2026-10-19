"""AI layer: rubric, schemas, evidence assembly, prompts and the AI service."""

from __future__ import annotations

from .evidence import Evidence, PageEvidence, build_evidence
from .masking import mask_contact_patterns, normalize_bio
from .rubric import (
    DEFAULT_RUBRIC,
    Rubric,
    RubricCriterion,
    compute_qualification,
    parse_rubric,
)
from .schemas import CriterionScore, DossierDraft, OutreachDraft
from .service import AIService, DossierResult

__all__ = [
    "AIService",
    "CriterionScore",
    "DEFAULT_RUBRIC",
    "DossierDraft",
    "DossierResult",
    "Evidence",
    "OutreachDraft",
    "PageEvidence",
    "Rubric",
    "RubricCriterion",
    "build_evidence",
    "compute_qualification",
    "mask_contact_patterns",
    "normalize_bio",
    "parse_rubric",
]
