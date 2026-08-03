"""Deterministic, evidence-aware acquisition candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Disposition = Literal["eligible", "needs_evidence", "rejected"]
PriorityMode = Literal[
    "full_v1",
    "fit_quality_provisional_v1",
    "evidence_only_provisional_v1",
]


@dataclass(frozen=True)
class EligibilityFacts:
    country_status: Literal["confirmed", "unknown", "conflicting", "mismatch"]
    buyer_type_match: bool | None
    excluded_business: bool
    independent_identity: bool
    product_evidence: bool | None
    contact_path: bool | None
    duplicate: bool = False
    suppressed: bool = False
    policy_blocked: bool = False
    stale_source: bool = False


@dataclass(frozen=True)
class GateResult:
    disposition: Disposition
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ScoreInput:
    product_relevance: int | None
    buyer_role: int | None
    country_match: int | None
    company_size: int | None
    industry_match: int | None
    direct_purchase: int | None
    recent_activity: int | None
    competitor_signal: int | None
    signal_recency: int | None
    identity_quality: int | None
    source_trust: int | None
    contactability: int | None
    independent_evidence: int | None
    data_recency: int | None


@dataclass(frozen=True)
class ScoreResult:
    fit_score: int | None
    intent_score: int | None
    data_quality_score: int | None
    priority_score: int | None
    priority_band: str
    signal_coverage: int
    priority_mode: PriorityMode


def evaluate_gate(facts: EligibilityFacts) -> GateResult:
    """Apply hard rejections before returning a request for more evidence."""

    rejected: list[str] = []
    if facts.policy_blocked:
        rejected.append("policy_blocked")
    if facts.suppressed:
        rejected.append("suppressed")
    if facts.duplicate:
        rejected.append("duplicate")
    if facts.country_status == "mismatch":
        rejected.append("wrong_country")
    if facts.buyer_type_match is False:
        rejected.append("wrong_buyer_type")
    if facts.excluded_business:
        rejected.append("excluded_business")
    if not facts.independent_identity:
        rejected.append("no_independent_identity")
    if facts.product_evidence is False:
        rejected.append("insufficient_product_evidence")
    if facts.contact_path is False:
        rejected.append("no_contact_path")
    if facts.stale_source:
        rejected.append("stale_source")
    if rejected:
        return GateResult("rejected", tuple(rejected))
    unknown: list[str] = []
    if facts.country_status in {"unknown", "conflicting"}:
        unknown.append(f"country_{facts.country_status}")
    if facts.buyer_type_match is None:
        unknown.append("buyer_type_unknown")
    if facts.product_evidence is None:
        unknown.append("product_evidence_unknown")
    if facts.contact_path is None:
        unknown.append("contact_path_unknown")
    if unknown:
        return GateResult("needs_evidence", tuple(unknown))
    return GateResult("eligible", ())


def _weighted_known(
    items: tuple[tuple[int | None, int], ...],
) -> tuple[int | None, int]:
    known = [(value, weight) for value, weight in items if value is not None]
    if not known:
        return None, 0
    for value, _weight in known:
        if value < 0 or value > 100:
            raise ValueError("score signals must be between 0 and 100")
    known_weight = sum(weight for _value, weight in known)
    total_weight = sum(weight for _value, weight in items)
    score = round(sum(value * weight for value, weight in known) / known_weight)
    coverage = round(100 * known_weight / total_weight)
    return score, coverage


def _band(score: int | None, coverage: int, mode: PriorityMode) -> str:
    if score is None:
        return "unknown"
    if mode != "full_v1":
        return "B" if score >= 55 else "C"
    if score >= 85 and coverage >= 60 and mode == "full_v1":
        return "S"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    return "C"


def score_candidate(value: ScoreInput) -> ScoreResult:
    """Score known signals only and report how much evidence was available."""

    fit, fit_coverage = _weighted_known(
        (
            (value.product_relevance, 35),
            (value.buyer_role, 25),
            (value.country_match, 20),
            (value.company_size, 10),
            (value.industry_match, 10),
        )
    )
    intent, intent_coverage = _weighted_known(
        (
            (value.direct_purchase, 40),
            (value.recent_activity, 25),
            (value.competitor_signal, 20),
            (value.signal_recency, 15),
        )
    )
    quality, quality_coverage = _weighted_known(
        (
            (value.identity_quality, 25),
            (value.source_trust, 25),
            (value.contactability, 20),
            (value.independent_evidence, 15),
            (value.data_recency, 15),
        )
    )
    priority, _dimension_coverage = _weighted_known(((fit, 50), (intent, 30), (quality, 20)))
    total_coverage = round((fit_coverage * 50 + intent_coverage * 30 + quality_coverage * 20) / 100)
    if intent is not None:
        mode: PriorityMode = "full_v1"
    elif any(
        item is not None
        for item in (value.product_relevance, value.buyer_role, value.industry_match)
    ):
        mode = "fit_quality_provisional_v1"
    else:
        mode = "evidence_only_provisional_v1"
        # Evidence quality tells us whether a source is usable; by itself it says
        # nothing about whether the company is a good lead. Keep that quality
        # score visible, but do not turn it into a misleading lead priority.
        priority = None
    return ScoreResult(
        fit_score=fit,
        intent_score=intent,
        data_quality_score=quality,
        priority_score=priority,
        priority_band=_band(priority, total_coverage, mode),
        signal_coverage=total_coverage,
        priority_mode=mode,
    )
