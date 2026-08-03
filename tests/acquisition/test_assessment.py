from __future__ import annotations

import json

from app.modules.acquisition.models import (
    AcquisitionCandidate,
    AcquisitionMission,
    CandidateEvidence,
)


def _mission() -> AcquisitionMission:
    return AcquisitionMission(
        id="mission-1",
        tenant_id="tenant-1",
        name="MX motorcycle distributors",
        product_snapshot_id="product-1",
        target_profile_json=json.dumps(
            {
                "country_codes": ["MX"],
                "buyer_types": ["distributor"],
                "exclude_terms": ["marketplace"],
            }
        ),
        created_by="user-1",
    )


def _candidate(**overrides) -> AcquisitionCandidate:
    values = {
        "id": "candidate-1",
        "tenant_id": "tenant-1",
        "mission_id": "mission-1",
        "company_name": "Moto Dealer",
        "domain": "moto.example",
        "website": "https://moto.example/",
        "country_resolution_status": "unknown",
        "opportunity_country_code": "",
        "contact_json": "{}",
        "observed_facts_json": "[]",
        "dedupe_key": "moto.example",
    }
    values.update(overrides)
    return AcquisitionCandidate(**values)


def _evidence(
    *,
    suffix: str = "1",
    canonical_url: str = "https://moto.example/",
    trust_tier: str = "D",
    validation_status: str = "unverified",
    source_type: str = "web_search",
) -> CandidateEvidence:
    return CandidateEvidence(
        id=f"evidence-{suffix}",
        tenant_id="tenant-1",
        candidate_id="candidate-1",
        provider="mimo",
        source_type=source_type,
        trust_tier=trust_tier,
        source_url=canonical_url,
        canonical_url=canonical_url,
        title="Moto Dealer",
        excerpt="Wholesale motorcycle parts in Mexico",
        content_hash=suffix * 64,
        validation_status=validation_status,
    )


def test_search_evidence_only_creates_bounded_provisional_computation():
    from app.modules.acquisition.assessment import compute_candidate_assessment

    result = compute_candidate_assessment(
        _candidate(),
        _mission(),
        [_evidence()],
        mimo_model_id="mimo-v2.5-pro",
    )

    assert result.extraction_complete is False
    assert result.gate.disposition == "needs_evidence"
    assert result.score.priority_mode == "evidence_only_provisional_v1"
    assert result.score.priority_band == "B"
    assert result.model_provider == "deterministic"
    assert result.model_id == "evidence-only-v1"
    assert "临时评估" in result.explanation


def test_valid_official_evidence_and_facts_create_fit_assessment():
    from app.modules.acquisition.assessment import compute_candidate_assessment

    candidate = _candidate(
        country_resolution_status="confirmed",
        opportunity_country_code="MX",
        contact_json=json.dumps({"paths": ["https://moto.example/contact"]}),
        observed_facts_json=json.dumps(
            {
                "buyer_type": "distributor",
                "product_terms": ["motorcycle engines"],
                "claims": [{"text": "Wholesale motorcycle engines"}],
            }
        ),
    )
    result = compute_candidate_assessment(
        candidate,
        _mission(),
        [_evidence(trust_tier="A", validation_status="valid")],
        mimo_model_id="mimo-v2.5-pro",
    )

    assert result.extraction_complete is True
    assert result.gate.disposition == "eligible"
    assert result.score.priority_mode == "fit_quality_provisional_v1"
    assert result.score.priority_band == "B"
    assert result.model_provider == "mimo"
    assert result.model_id == "mimo-v2.5-pro"


def test_unreachable_error_evidence_is_excluded_from_trust_scoring():
    from app.modules.acquisition.assessment import compute_candidate_assessment

    result = compute_candidate_assessment(
        _candidate(),
        _mission(),
        [
            _evidence(
                trust_tier="E",
                validation_status="unreachable",
                source_type="fetch_error",
            )
        ],
        mimo_model_id="mimo-v2.5-pro",
    )

    assert result.score_input.source_trust is None
    assert result.score_input.data_recency is None


def test_duplicate_canonical_url_counts_as_one_independent_source():
    from app.modules.acquisition.assessment import compute_candidate_assessment

    result = compute_candidate_assessment(
        _candidate(),
        _mission(),
        [
            _evidence(suffix="1"),
            _evidence(suffix="2", trust_tier="A", validation_status="valid"),
        ],
        mimo_model_id="mimo-v2.5-pro",
    )

    assert result.score_input.independent_evidence == 50


def test_confirmed_buyer_mismatch_remains_hard_rejection():
    from app.modules.acquisition.assessment import compute_candidate_assessment

    candidate = _candidate(
        country_resolution_status="confirmed",
        opportunity_country_code="MX",
        observed_facts_json=json.dumps(
            {
                "buyer_type": "retailer",
                "product_terms": ["motorcycle parts"],
                "claims": [{"text": "Retail motorcycle parts"}],
            }
        ),
    )
    result = compute_candidate_assessment(
        candidate,
        _mission(),
        [_evidence(trust_tier="A", validation_status="valid")],
        mimo_model_id="mimo-v2.5-pro",
    )

    assert result.gate.disposition == "rejected"
    assert "wrong_buyer_type" in result.gate.reason_codes
    assert "目标买家类型" in result.explanation
    assert "thought" not in result.explanation.lower()
