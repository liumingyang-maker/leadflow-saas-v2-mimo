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


def test_radar_run_and_snapshot_persist_bounded_defaults(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun, RadarSnapshot

    run = RadarRun(
        id="run-a",
        tenant_id="tenant-a",
        profile_id="profile-a",
        root_job_id="job-a",
        requested_by="actor-a",
        budget_json='{"pages":10,"wall_seconds":300}',
    )
    snapshot = RadarSnapshot(
        id="snapshot-a",
        tenant_id="tenant-a",
        profile_id="profile-a",
        run_id="run-a",
        page_kind="home",
        requested_url="https://rival.example/",
        canonical_url="https://rival.example/",
        content_hash="a" * 64,
        facts_json="[]",
        excerpt="bounded excerpt",
    )

    with Session(get_engine(radar_app)) as session:
        session.add_all((run, snapshot))
        session.commit()
        session.refresh(run)
        session.refresh(snapshot)

        assert run.status == "queued"
        assert run.stage == "queued"
        assert run.result_summary_json == "{}"
        assert snapshot.source_method == "static"
        assert snapshot.validation_status == "valid"
