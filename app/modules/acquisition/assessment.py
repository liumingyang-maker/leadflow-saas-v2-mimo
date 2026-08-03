"""Pure evidence-aware assessment computation shared by every write path."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from app.modules.acquisition.models import (
    AcquisitionCandidate,
    AcquisitionMission,
    CandidateEvidence,
)
from app.modules.acquisition.policies import canonical_json
from app.modules.acquisition.scoring import (
    EligibilityFacts,
    GateResult,
    ScoreInput,
    ScoreResult,
    evaluate_gate,
    score_candidate,
)
from app.modules.acquisition.versions import (
    EVIDENCE_ONLY_PROMPT_VERSION,
    MIMO_EXTRACT_PROMPT_VERSION,
)

_TRUST_VALUES = {"A": 100, "B": 80, "C": 60, "D": 40, "E": 20}
_USABLE_EVIDENCE_STATUSES = {"valid", "unverified"}


@dataclass(frozen=True)
class AssessmentComputation:
    gate: GateResult
    score_input: ScoreInput
    score: ScoreResult
    evidence_bundle_hash: str
    prompt_version: str
    model_provider: str
    model_id: str
    explanation: str
    extraction_complete: bool


def compute_candidate_assessment(
    candidate: AcquisitionCandidate,
    mission: AcquisitionMission,
    evidence_items: Sequence[CandidateEvidence],
    *,
    mimo_model_id: str,
) -> AssessmentComputation:
    target = _json_object(mission.target_profile_json)
    observed = _json_object(candidate.observed_facts_json)
    contact = _json_object(candidate.contact_json)
    usable = tuple(
        item for item in evidence_items if item.validation_status in _USABLE_EVIDENCE_STATUSES
    )
    extraction_complete = {"buyer_type", "product_terms", "claims"}.issubset(observed)

    buyer_type = str(observed.get("buyer_type", "")).lower()
    expected_buyers = {str(item).lower() for item in target.get("buyer_types", [])}
    buyer_match = None
    if buyer_type:
        buyer_match = not expected_buyers or buyer_type in expected_buyers

    product_terms = [str(item) for item in observed.get("product_terms", [])]
    claims = list(observed.get("claims", []))
    contact_paths = [str(item) for item in contact.get("paths", [])]
    if contact.get("email"):
        contact_paths.append(str(contact["email"]))

    target_countries = {str(item).upper() for item in target.get("country_codes", [])}
    gate_country = candidate.country_resolution_status
    if (
        gate_country == "confirmed"
        and target_countries
        and candidate.opportunity_country_code not in target_countries
    ):
        gate_country = "mismatch"

    combined = " ".join(
        [candidate.company_name, buyer_type, *product_terms, json.dumps(claims)]
    ).lower()
    excluded = any(str(term).lower() in combined for term in target.get("exclude_terms", []))
    gate = evaluate_gate(
        EligibilityFacts(
            country_status=gate_country,
            buyer_type_match=buyer_match,
            excluded_business=excluded,
            independent_identity=bool(candidate.company_name and candidate.domain),
            product_evidence=True if product_terms or claims else None,
            contact_path=True if contact_paths else None,
        )
    )

    best_trust = max(
        (_TRUST_VALUES.get(item.trust_tier, 0) for item in usable),
        default=0,
    )
    unique_sources = {item.canonical_url for item in usable if item.canonical_url}
    score_input = ScoreInput(
        product_relevance=85 if product_terms else None,
        buyer_role=85 if buyer_match is True else (0 if buyer_match is False else None),
        country_match=(
            100 if gate_country == "confirmed" else (0 if gate_country == "mismatch" else None)
        ),
        company_size=None,
        industry_match=70 if product_terms else None,
        direct_purchase=None,
        recent_activity=None,
        competitor_signal=None,
        signal_recency=None,
        identity_quality=90 if candidate.company_name and candidate.domain else None,
        source_trust=best_trust or None,
        contactability=80 if contact_paths else None,
        independent_evidence=(80 if len(unique_sources) >= 2 else (50 if unique_sources else None)),
        data_recency=90 if usable else None,
    )
    score = score_candidate(score_input)
    evidence_bundle_hash = hashlib.sha256(
        canonical_json(
            sorted(
                (item.canonical_url, item.content_hash, item.validation_status) for item in usable
            )
        ).encode("utf-8")
    ).hexdigest()
    prompt_version = (
        MIMO_EXTRACT_PROMPT_VERSION if extraction_complete else EVIDENCE_ONLY_PROMPT_VERSION
    )
    model_provider = "mimo" if extraction_complete else "deterministic"
    model_id = mimo_model_id if extraction_complete else EVIDENCE_ONLY_PROMPT_VERSION
    return AssessmentComputation(
        gate=gate,
        score_input=score_input,
        score=score,
        evidence_bundle_hash=evidence_bundle_hash,
        prompt_version=prompt_version,
        model_provider=model_provider,
        model_id=model_id,
        explanation=_explain_assessment(gate, extraction_complete=extraction_complete),
        extraction_complete=extraction_complete,
    )


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _explain_assessment(gate: GateResult, *, extraction_complete: bool) -> str:
    if gate.disposition == "rejected":
        reason = gate.reason_codes[0] if gate.reason_codes else ""
        return {
            "wrong_country": "公开证据显示目标国家不匹配。",
            "wrong_buyer_type": "公开证据显示该企业不是目标买家类型。",
            "excluded_business": "公开证据命中了排除业务类型。",
            "no_independent_identity": "尚未确认独立企业身份。",
            "insufficient_product_evidence": "公开证据未显示目标产品相关性。",
            "no_contact_path": "公开证据确认缺少可用联系方式。",
        }.get(reason, "公开证据未通过当前资格门禁。")
    if not extraction_complete:
        return "当前为临时评估；官网验证或结构化分析尚未完成，请重新验证。"
    if gate.disposition == "needs_evidence":
        return "基础信息具有相关性，但国家、买家角色或联系方式仍需补充证据。"
    return "公开证据符合当前目标市场和买家类型。"
