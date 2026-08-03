from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_radar_models_persist_safe_initial_statuses(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import CompetitorProfile, RadarCompetitorSuggestion

    profile = CompetitorProfile(
        tenant_id="tenant-a",
        mission_id="mission-a",
        product_snapshot_id="snapshot-a",
        company_name="Acme Rival",
        canonical_domain="rival.example",
        official_url="https://rival.example/",
    )
    suggestion = RadarCompetitorSuggestion(
        tenant_id="tenant-a",
        mission_id="mission-a",
        company_name="Acme Rival",
        canonical_domain="rival.example",
        official_url="https://rival.example/",
        evidence_hash="a" * 64,
    )

    with Session(get_engine(radar_app)) as session:
        session.add_all((profile, suggestion))
        session.commit()
        session.refresh(profile)
        session.refresh(suggestion)

        assert profile.status == "active"
        assert profile.tracking_config_json == "{}"
        assert suggestion.status == "proposed"
        assert suggestion.reason_codes_json == "[]"
        assert suggestion.evidence_json == "[]"


def test_suggestion_rejects_duplicate_domain_within_tenant_mission(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import RadarCompetitorSuggestion

    values = {
        "tenant_id": "tenant-a",
        "mission_id": "mission-a",
        "company_name": "Acme Rival",
        "canonical_domain": "rival.example",
        "official_url": "https://rival.example/",
        "evidence_hash": "a" * 64,
    }
    with Session(get_engine(radar_app)) as session:
        session.add(RadarCompetitorSuggestion(**values))
        session.commit()
        session.add(RadarCompetitorSuggestion(**values))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("tenant/mission/domain uniqueness must be enforced")


def test_profile_rejects_duplicate_domain_within_tenant_mission(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import CompetitorProfile

    values = {
        "tenant_id": "tenant-a",
        "mission_id": "mission-a",
        "product_snapshot_id": "snapshot-a",
        "company_name": "Acme Rival",
        "canonical_domain": "rival.example",
        "official_url": "https://rival.example/",
    }
    with Session(get_engine(radar_app)) as session:
        session.add(CompetitorProfile(**values))
        session.commit()
        session.add(CompetitorProfile(**values))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("tenant/mission/domain uniqueness must be enforced")
