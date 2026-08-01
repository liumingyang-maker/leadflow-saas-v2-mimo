from __future__ import annotations

import pytest


def test_invalid_acquisition_budget_fails_closed(monkeypatch):
    monkeypatch.setenv("ACQUISITION_MAX_CANDIDATES", "0")
    from app.config import resolve_config

    with pytest.raises(RuntimeError, match="ACQUISITION_MAX_CANDIDATES"):
        resolve_config("development")


def test_non_integer_acquisition_budget_fails_closed(monkeypatch):
    monkeypatch.setenv("ACQUISITION_MAX_VERIFY", "many")
    from app.config import resolve_config

    with pytest.raises(RuntimeError, match="ACQUISITION_MAX_VERIFY must be an integer"):
        resolve_config("development")


def test_acquisition_budget_defaults_are_bounded(monkeypatch):
    for name in (
        "ACQUISITION_MAX_CANDIDATES",
        "ACQUISITION_MAX_VERIFY",
        "ACQUISITION_MAX_SEARCH_ACTIONS",
        "FETCH_MAX_PAGES_PER_SITE",
    ):
        monkeypatch.delenv(name, raising=False)

    from app.config import resolve_config

    config = resolve_config("testing")
    assert config.ACQUISITION_MAX_CANDIDATES == 30
    assert config.ACQUISITION_MAX_VERIFY == 10
    assert config.ACQUISITION_MAX_SEARCH_ACTIONS == 5
    assert config.FETCH_MAX_PAGES_PER_SITE == 5


def test_mission_contract_rejects_invalid_country_and_buyer_type():
    from pydantic import ValidationError

    from app.modules.acquisition.contracts import MissionCreateInput

    with pytest.raises(ValidationError, match="invalid ISO alpha-2"):
        MissionCreateInput(
            product_snapshot_id="p1",
            country_codes=["ZZ"],
            buyer_types=["distributor"],
        )
    with pytest.raises(ValidationError, match="unsupported buyer types"):
        MissionCreateInput(
            product_snapshot_id="p1",
            country_codes=["MX"],
            buyer_types=["consumer"],
        )


def test_reject_decision_requires_structured_reason():
    from pydantic import ValidationError

    from app.modules.acquisition.contracts import CandidateDecisionInput

    with pytest.raises(ValidationError, match="reason_code is required"):
        CandidateDecisionInput(action="reject")


def test_target_profile_merges_default_exclusions_without_duplicates():
    from app.modules.acquisition.contracts import MissionCreateInput
    from app.modules.acquisition.policies import build_target_profile

    value = MissionCreateInput(
        product_snapshot_id="p1",
        country_codes=["MX"],
        buyer_types=["distributor"],
        exclude_terms=["marketplace", "retailer"],
    )
    profile = build_target_profile(value)
    assert profile["exclude_terms"] == [
        "electric only",
        "marketplace",
        "supplier",
        "retailer",
    ]
