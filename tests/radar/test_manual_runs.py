from __future__ import annotations

from sqlalchemy.orm import Session


def _enable_radar(app) -> None:
    from app.core.capabilities import Capability

    app.config["CAPABILITIES"][Capability.COMPETITOR_RADAR] = True


def _seed_profile(app, *, tenant_id: str = "tenant-a", mission_status: str = "running") -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot
    from app.modules.radar.models import CompetitorProfile

    with Session(get_engine(app)) as session:
        session.add(
            ProductKnowledgeSnapshot(
                id=f"snapshot-{tenant_id}",
                tenant_id=tenant_id,
                version="v1",
                product_name="Motorcycles",
                summary="Motorcycle engine distributor product",
                content_hash="a" * 64,
                approved_by="actor-a",
            )
        )
        session.add(
            AcquisitionMission(
                id=f"mission-{tenant_id}",
                tenant_id=tenant_id,
                name="Mission",
                status=mission_status,
                product_snapshot_id=f"snapshot-{tenant_id}",
                created_by="actor-a",
            )
        )
        session.add(
            CompetitorProfile(
                id=f"profile-{tenant_id}",
                tenant_id=tenant_id,
                mission_id=f"mission-{tenant_id}",
                product_snapshot_id=f"snapshot-{tenant_id}",
                company_name="Acme Rival",
                canonical_domain="rival.example",
                official_url="https://rival.example/",
            )
        )
        session.commit()


def test_manual_run_is_idempotent_while_active_and_persists_bounded_job(
    monkeypatch,
    radar_app,
) -> None:
    import app.modules.radar.service as service
    from app.extensions import get_engine
    from app.modules.jobs.models import Job

    _enable_radar(radar_app)
    _seed_profile(radar_app)
    monkeypatch.setattr(service, "enqueue_existing_job", lambda *_args, **_kwargs: None)

    first = service.request_manual_run(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        profile_id="profile-tenant-a",
    )
    second = service.request_manual_run(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        profile_id="profile-tenant-a",
    )

    assert first.id == second.id
    assert first.status == "queued"
    with Session(get_engine(radar_app)) as session:
        job = session.get(Job, first.root_job_id)
        assert job is not None
        assert job.tenant_id == "tenant-a"
        assert job.job_type == "radar_scan"
        assert job.payload_json == f'{{"run_id":"{first.id}"}}'


def test_terminal_mission_cannot_start_manual_radar_run(monkeypatch, radar_app) -> None:
    import pytest

    import app.modules.radar.service as service

    _enable_radar(radar_app)
    _seed_profile(radar_app, mission_status="completed")
    monkeypatch.setattr(service, "enqueue_existing_job", lambda *_args, **_kwargs: None)

    with pytest.raises(service.RadarServiceError, match="active"):
        service.request_manual_run(
            radar_app,
            tenant_id="tenant-a",
            actor_id="actor-a",
            profile_id="profile-tenant-a",
        )
