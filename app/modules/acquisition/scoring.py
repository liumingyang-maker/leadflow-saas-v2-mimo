"""Deterministic, evidence-aware acquisition candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Disposition = Literal["eligible", "needs_evidence", "rejected"]


@dataclass(frozen=True)
class EligibilityFacts:
    country_status: Literal["confirmed", "unknown", "conflicting", "mismatch"]
    buyer_type_match: bool
    excluded_business: bool
    independent_identity: bool
    product_evidence: bool
    contact_path: bool
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
    priority_mode: str


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
    if not facts.buyer_type_match:
        rejected.append("wrong_buyer_type")
    if facts.excluded_business:
        rejected.append("excluded_business")
    if not facts.independent_identity:
        rejected.append("no_independent_identity")
    if not facts.product_evidence:
        rejected.append("insufficient_product_evidence")
    if not facts.contact_path:
        rejected.append("no_contact_path")
    if facts.stale_source:
        rejected.append("stale_source")
    if rejected:
        return GateResult("rejected", tuple(rejected))
    if facts.country_status in {"unknown", "conflicting"}:
        return GateResult("needs_evidence", (f"country_{facts.country_status}",))
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


def _band(score: int | None, coverage: int) -> str:
    if score is None:
        return "unknown"
    if score >= 85 and coverage >= 60:
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
    mode = "full_v1" if intent is not None else "fit_quality_provisional_v1"
    return ScoreResult(
        fit_score=fit,
        intent_score=intent,
        data_quality_score=quality,
        priority_score=priority,
        priority_band=_band(priority, total_coverage),
        signal_coverage=total_coverage,
        priority_mode=mode,
    )
