from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def _valid_payload(
    *, evidence_excerpt: str = "Acme Rival sells engines through distributors."
) -> dict:
    return {
        "suggestions": [
            {
                "company_name": "Acme Rival",
                "official_url": "https://rival.example/",
                "reason_codes": ["same-product-category"],
                "evidence": [
                    {
                        "source_url": "https://source.example/directory",
                        "excerpt": evidence_excerpt,
                    }
                ],
            }
        ]
    }


class FakeProvider:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict] = []
        self.closed = False

    def suggest_competitors(self, *, product_summary: str, target_profile: dict) -> object:
        self.calls.append({"product_summary": product_summary, "target_profile": target_profile})
        return self.result

    def close(self) -> None:
        self.closed = True


def _enable_radar(app) -> None:
    from app.core.capabilities import Capability

    app.config["CAPABILITIES"][Capability.COMPETITOR_RADAR] = True
    app.config["CAPABILITIES"][Capability.AI_RESEARCH] = True


def _install_provider(monkeypatch, provider: FakeProvider) -> None:
    import app.modules.radar.service as radar_service
    import app.modules.radar.suggestions as radar_suggestions

    monkeypatch.setattr(radar_service, "build_mimo_provider", lambda _app, tenant_id: provider)
    monkeypatch.setattr(radar_suggestions, "system_resolver", _public_resolver)


def _stored_counts(app) -> tuple[int, int]:
    from app.extensions import get_engine
    from app.modules.radar.models import CompetitorProfile, RadarCompetitorSuggestion

    with Session(get_engine(app)) as session:
        return (
            session.scalar(select(func.count()).select_from(RadarCompetitorSuggestion)) or 0,
            session.scalar(select(func.count()).select_from(CompetitorProfile)) or 0,
        )


def test_competitor_contract_rejects_confidence_and_uncited_proposals() -> None:
    from app.integrations.ai.contracts import CompetitorSuggestionResults

    payload = _valid_payload()
    payload["suggestions"][0]["confidence"] = 0.99
    with pytest.raises(ValidationError):
        CompetitorSuggestionResults.model_validate(payload)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload["suggestions"][0].update(company_name="   "),
        lambda payload: payload["suggestions"][0].update(reason_codes=["  \t "]),
        lambda payload: payload["suggestions"][0]["evidence"][0].update(excerpt="  \n "),
    ),
)
def test_competitor_contract_rejects_blank_values_after_normalization(mutate) -> None:
    from app.integrations.ai.contracts import CompetitorSuggestionResults

    payload = _valid_payload()
    mutate(payload)
    with pytest.raises(ValidationError):
        CompetitorSuggestionResults.model_validate(payload)


def test_competitor_contract_bounds_all_persisted_urls() -> None:
    from app.integrations.ai.contracts import CompetitorSuggestionResults

    payload = _valid_payload()
    payload["suggestions"][0]["official_url"] = "https://rival.example/" + ("a" * 1000)
    with pytest.raises(ValidationError):
        CompetitorSuggestionResults.model_validate(payload)

    payload = _valid_payload()
    payload["suggestions"][0]["evidence"][0]["source_url"] = "https://source.example/" + (
        "a" * 1000
    )
    with pytest.raises(ValidationError):
        CompetitorSuggestionResults.model_validate(payload)

    payload = _valid_payload()
    payload["suggestions"][0]["evidence"] = []
    with pytest.raises(ValidationError):
        CompetitorSuggestionResults.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    (
        {"suggestions": [{**_valid_payload()["suggestions"][0], "evidence": []}]},
        {
            "suggestions": [
                {**_valid_payload()["suggestions"][0], "official_url": "http://localhost/"}
            ]
        },
        {
            "suggestions": [
                {
                    **_valid_payload()["suggestions"][0],
                    "evidence": [{"source_url": "http://localhost/", "excerpt": "Unsafe source"}],
                }
            ]
        },
        {"suggestions": [_valid_payload()["suggestions"][0]] * 11},
    ),
)
def test_request_never_persists_invalid_or_unsafe_proposals(
    monkeypatch, radar_app, seed_radar_mission, payload
) -> None:
    from app.modules.radar.service import RadarServiceError, request_competitor_suggestions

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(payload)
    _install_provider(monkeypatch, provider)

    with pytest.raises(RadarServiceError):
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
        )
    assert _stored_counts(radar_app) == (0, 0)


def test_request_rejects_foreign_or_inactive_mission_before_calling_provider(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.modules.radar.policies import RadarPolicyError
    from app.modules.radar.service import RadarNotFoundError, request_competitor_suggestions

    _enable_radar(radar_app)
    seed_radar_mission(tenant_id="tenant-a", mission_id="mission-a", status="draft")
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)

    with pytest.raises(RadarNotFoundError):
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-b", actor_id="owner-b", mission_id="mission-a"
        )
    with pytest.raises(RadarPolicyError, match="active"):
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
        )
    assert provider.calls == []


def test_request_persists_valid_cited_suggestion_and_closes_provider(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import RadarCompetitorSuggestion
    from app.modules.radar.service import request_competitor_suggestions

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)

    suggestion_ids = request_competitor_suggestions(
        radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
    )

    assert len(suggestion_ids) == 1
    assert provider.closed is True
    with Session(get_engine(radar_app)) as session:
        stored = session.get(RadarCompetitorSuggestion, suggestion_ids[0])
        assert stored is not None
        assert stored.tenant_id == "tenant-a"
        assert stored.canonical_domain == "rival.example"
        assert stored.evidence_json == (
            '[{"excerpt":"Acme Rival sells engines through distributors.",'
            '"source_url":"https://source.example/directory"}]'
        )


def test_request_rejects_evidence_that_does_not_name_the_competitor(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.modules.radar.service import RadarServiceError, request_competitor_suggestions

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload(evidence_excerpt="The weather will be sunny tomorrow."))
    _install_provider(monkeypatch, provider)

    with pytest.raises(RadarServiceError):
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
        )
    assert _stored_counts(radar_app) == (0, 0)


def test_request_rejects_evidence_unrelated_to_the_mission_product(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.modules.radar.service import RadarServiceError, request_competitor_suggestions

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(
        _valid_payload(evidence_excerpt="Acme Rival publishes local weather forecasts.")
    )
    _install_provider(monkeypatch, provider)

    with pytest.raises(RadarServiceError):
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
        )
    assert _stored_counts(radar_app) == (0, 0)


def test_dismissal_is_terminal_until_evidence_changes(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import RadarCompetitorSuggestion
    from app.modules.radar.service import (
        decide_competitor_suggestion,
        request_competitor_suggestions,
    )

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)
    suggestion_id = request_competitor_suggestions(
        radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
    )[0]

    assert (
        decide_competitor_suggestion(
            radar_app,
            tenant_id="tenant-a",
            actor_id="owner-a",
            suggestion_id=suggestion_id,
            action="dismiss",
        )
        is None
    )
    assert (
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
        )
        == ()
    )

    provider.result = _valid_payload(
        evidence_excerpt="Acme Rival has new cited evidence offering motorcycle engines."
    )
    assert request_competitor_suggestions(
        radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
    ) == (suggestion_id,)
    with Session(get_engine(radar_app)) as session:
        assert session.get(RadarCompetitorSuggestion, suggestion_id).status == "proposed"


def test_approval_is_atomic_and_idempotent(monkeypatch, radar_app, seed_radar_mission) -> None:
    from app.extensions import get_engine
    from app.modules.audit.models import AuditEvent
    from app.modules.radar.service import (
        decide_competitor_suggestion,
        request_competitor_suggestions,
    )

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)
    suggestion_id = request_competitor_suggestions(
        radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
    )[0]

    first = decide_competitor_suggestion(
        radar_app,
        tenant_id="tenant-a",
        actor_id="owner-a",
        suggestion_id=suggestion_id,
        action="approve",
    )
    second = decide_competitor_suggestion(
        radar_app,
        tenant_id="tenant-a",
        actor_id="owner-a",
        suggestion_id=suggestion_id,
        action="approve",
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert _stored_counts(radar_app) == (1, 1)
    with Session(get_engine(radar_app)) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "radar.profile_approved")
            )
            == 1
        )


def test_repeated_approval_preserves_original_decision_provenance(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import RadarCompetitorSuggestion
    from app.modules.radar.service import (
        decide_competitor_suggestion,
        request_competitor_suggestions,
    )

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)
    suggestion_id = request_competitor_suggestions(
        radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
    )[0]
    decide_competitor_suggestion(
        radar_app,
        tenant_id="tenant-a",
        actor_id="owner-a",
        suggestion_id=suggestion_id,
        action="approve",
    )
    with Session(get_engine(radar_app)) as session:
        original = session.get(RadarCompetitorSuggestion, suggestion_id)
        assert original is not None
        original_decided_at = original.decided_at

    decide_competitor_suggestion(
        radar_app,
        tenant_id="tenant-a",
        actor_id="owner-b",
        suggestion_id=suggestion_id,
        action="approve",
    )
    with Session(get_engine(radar_app)) as session:
        stored = session.get(RadarCompetitorSuggestion, suggestion_id)
        assert stored is not None
        assert stored.decided_by == "owner-a"
        assert stored.decided_at == original_decided_at


def test_concurrent_approval_recovers_existing_tenant_profile(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import CompetitorProfile
    from app.modules.radar.repository import CompetitorProfileRepository
    from app.modules.radar.service import (
        decide_competitor_suggestion,
        request_competitor_suggestions,
    )

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)
    suggestion_id = request_competitor_suggestions(
        radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
    )[0]
    original_add = CompetitorProfileRepository.add

    def conflict_after_concurrent_insert(self, profile, *, tenant_id: str):
        with Session(get_engine(radar_app)) as concurrent:
            concurrent.add(
                CompetitorProfile(
                    id="concurrent-profile",
                    tenant_id=tenant_id,
                    mission_id=profile.mission_id,
                    product_snapshot_id=profile.product_snapshot_id,
                    source_suggestion_id=profile.source_suggestion_id,
                    company_name=profile.company_name,
                    canonical_domain=profile.canonical_domain,
                    official_url=profile.official_url,
                    tracking_config_json=profile.tracking_config_json,
                    approved_by="owner-b",
                )
            )
            concurrent.commit()
        monkeypatch.setattr(CompetitorProfileRepository, "add", original_add)
        raise IntegrityError("INSERT competitor_profiles", {}, RuntimeError("unique conflict"))

    monkeypatch.setattr(CompetitorProfileRepository, "add", conflict_after_concurrent_insert)
    profile = decide_competitor_suggestion(
        radar_app,
        tenant_id="tenant-a",
        actor_id="owner-a",
        suggestion_id=suggestion_id,
        action="approve",
    )

    assert profile is not None
    assert profile.id == "concurrent-profile"
    assert _stored_counts(radar_app) == (1, 1)


def test_concurrent_request_recovers_existing_tenant_suggestion(
    monkeypatch, radar_app, seed_radar_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import RadarCompetitorSuggestion
    from app.modules.radar.repository import RadarSuggestionRepository
    from app.modules.radar.service import request_competitor_suggestions

    _enable_radar(radar_app)
    seed_radar_mission()
    provider = FakeProvider(_valid_payload())
    _install_provider(monkeypatch, provider)
    original_add = RadarSuggestionRepository.add

    def conflict_after_concurrent_insert(self, suggestion, *, tenant_id: str):
        with Session(get_engine(radar_app)) as concurrent:
            concurrent.add(
                RadarCompetitorSuggestion(
                    id="concurrent-suggestion",
                    tenant_id=tenant_id,
                    mission_id=suggestion.mission_id,
                    company_name=suggestion.company_name,
                    canonical_domain=suggestion.canonical_domain,
                    official_url=suggestion.official_url,
                    reason_codes_json=suggestion.reason_codes_json,
                    evidence_json=suggestion.evidence_json,
                    evidence_hash=suggestion.evidence_hash,
                )
            )
            concurrent.commit()
        monkeypatch.setattr(RadarSuggestionRepository, "add", original_add)
        raise IntegrityError(
            "INSERT radar_competitor_suggestions", {}, RuntimeError("unique conflict")
        )

    monkeypatch.setattr(RadarSuggestionRepository, "add", conflict_after_concurrent_insert)
    assert (
        request_competitor_suggestions(
            radar_app, tenant_id="tenant-a", actor_id="owner-a", mission_id="mission-a"
        )
        == ()
    )
    assert _stored_counts(radar_app) == (1, 0)
