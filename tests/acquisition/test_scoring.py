from __future__ import annotations

import pytest


def test_unknown_country_needs_evidence_not_rejection():
    from app.modules.acquisition.scoring import EligibilityFacts, evaluate_gate

    result = evaluate_gate(
        EligibilityFacts(
            country_status="unknown",
            buyer_type_match=True,
            excluded_business=False,
            independent_identity=True,
            product_evidence=True,
            contact_path=True,
        )
    )
    assert result.disposition == "needs_evidence"
    assert result.reason_codes == ("country_unknown",)


def test_missing_intent_is_provisional_not_zero():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    result = score_candidate(
        ScoreInput(
            product_relevance=90,
            buyer_role=80,
            country_match=100,
            company_size=None,
            industry_match=70,
            direct_purchase=None,
            recent_activity=None,
            competitor_signal=None,
            signal_recency=None,
            identity_quality=90,
            source_trust=80,
            contactability=70,
            independent_evidence=80,
            data_recency=60,
        )
    )
    assert result.intent_score is None
    assert result.priority_mode == "fit_quality_provisional_v1"
    assert result.priority_score is not None and result.priority_score > 0
    assert result.signal_coverage < 100


def test_provisional_priority_cannot_receive_s_band():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    result = score_candidate(
        ScoreInput(
            product_relevance=100,
            buyer_role=100,
            country_match=100,
            company_size=100,
            industry_match=100,
            direct_purchase=None,
            recent_activity=None,
            competitor_signal=None,
            signal_recency=None,
            identity_quality=100,
            source_trust=100,
            contactability=100,
            independent_evidence=100,
            data_recency=100,
        )
    )

    assert result.priority_mode == "fit_quality_provisional_v1"
    assert result.priority_band == "A"


def test_full_priority_can_receive_s_band():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    result = score_candidate(
        ScoreInput(**{field: 100 for field in ScoreInput.__dataclass_fields__})
    )

    assert result.priority_mode == "full_v1"
    assert result.priority_band == "S"


def test_hard_rejections_take_precedence_over_country_unknown():
    from app.modules.acquisition.scoring import EligibilityFacts, evaluate_gate

    result = evaluate_gate(
        EligibilityFacts(
            country_status="unknown",
            buyer_type_match=True,
            excluded_business=False,
            independent_identity=True,
            product_evidence=True,
            contact_path=True,
            policy_blocked=True,
        )
    )
    assert result.disposition == "rejected"
    assert result.reason_codes == ("policy_blocked",)


def test_same_score_input_is_reproducible():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    values = ScoreInput(*([75] * 14))
    assert score_candidate(values) == score_candidate(values)


def test_signal_out_of_range_is_rejected():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    values = ScoreInput(101, *([50] * 13))
    with pytest.raises(ValueError, match="between 0 and 100"):
        score_candidate(values)


def test_low_coverage_cannot_receive_s_band():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    values = ScoreInput(
        100,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        100,
        None,
        None,
        None,
        None,
    )
    result = score_candidate(values)
    assert result.priority_score == 100
    assert result.signal_coverage < 60
    assert result.priority_band == "A"
