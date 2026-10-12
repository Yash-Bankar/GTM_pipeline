"""Qualification rubric.

The rubric is the deterministic scoring layer: the model returns a 0-100 score
per criterion, and this module computes the weighted total and tier. The default
rubric can be overridden with ``AI_RUBRIC_JSON``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class RubricCriterion:
    name: str
    weight: float
    description: str


@dataclass(frozen=True)
class Rubric:
    name: str
    version: str
    criteria: tuple[RubricCriterion, ...]

    @property
    def total_weight(self) -> float:
        return sum(c.weight for c in self.criteria) or 1.0

    def criterion_names(self) -> list[str]:
        return [c.name for c in self.criteria]

    def to_prompt(self) -> str:
        return "\n".join(
            f"- {c.name} (weight {c.weight:g}): {c.description}" for c in self.criteria
        )


DEFAULT_RUBRIC = Rubric(
    name="synpo_finance_creator",
    version="1",
    criteria=(
        RubricCriterion(
            "finance_relevance",
            0.30,
            "How clearly the creator covers personal finance, investing or money topics.",
        ),
        RubricCriterion(
            "audience_fit",
            0.20,
            "Fit with a finance/money audience, only if supported by evidence.",
        ),
        RubricCriterion(
            "contactability",
            0.20,
            "Presence of a public email, phone, or a working contact page.",
        ),
        RubricCriterion(
            "activity",
            0.15,
            "Recent, consistent public posting activity.",
        ),
        RubricCriterion(
            "brand_safety",
            0.15,
            "Absence of adult/gambling/misleading content; generally brand-safe.",
        ),
    ),
)

TIER_THRESHOLDS: tuple[tuple[int, str], ...] = ((80, "A"), (60, "B"), (40, "C"), (0, "D"))


def parse_rubric(raw: str) -> Rubric | None:
    """Parse an ``AI_RUBRIC_JSON`` override; return None when blank/invalid."""
    if not raw or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
        criteria = tuple(
            RubricCriterion(
                name=str(item["name"]),
                weight=float(item.get("weight", 1.0)),
                description=str(item.get("description", "")),
            )
            for item in payload["criteria"]
        )
        if not criteria:
            return None
        return Rubric(
            name=str(payload.get("name", "custom")),
            version=str(payload.get("version", "1")),
            criteria=criteria,
        )
    except (ValueError, KeyError, TypeError):
        return None


def _clamp(value: object) -> int:
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def compute_qualification(
    scores: dict[str, int], rubric: Rubric
) -> tuple[int, str]:
    """Return ``(weighted_score_0_100, tier)`` for per-criterion scores."""
    total = 0.0
    for criterion in rubric.criteria:
        total += _clamp(scores.get(criterion.name, 0)) * criterion.weight
    weighted = total / rubric.total_weight
    overall = max(0, min(100, int(round(weighted))))
    tier = next(label for threshold, label in TIER_THRESHOLDS if overall >= threshold)
    return overall, tier
