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


def test_database_allows_only_one_active_run_per_profile(radar_app) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun

    _seed_profile(radar_app)
    with Session(get_engine(radar_app)) as session:
        session.add_all(
            (
                RadarRun(
                    id="active-run-a",
                    tenant_id="tenant-a",
                    profile_id="profile-tenant-a",
                    root_job_id="job-a",
                    requested_by="actor-a",
                    active_key="active",
                    budget_json='{"pages":10}',
                ),
                RadarRun(
                    id="active-run-b",
                    tenant_id="tenant-a",
                    profile_id="profile-tenant-a",
                    root_job_id="job-b",
                    requested_by="actor-a",
                    active_key="active",
                    budget_json='{"pages":10}',
                ),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_cancelling_an_active_run_cancels_its_job_and_archives_its_notification(
    monkeypatch,
    radar_app,
) -> None:
    import app.modules.radar.service as service
    from app.extensions import get_engine
    from app.modules.acquisition.models import Notification
    from app.modules.jobs.models import Job

    _enable_radar(radar_app)
    _seed_profile(radar_app)
    monkeypatch.setattr(service, "enqueue_existing_job", lambda *_args, **_kwargs: None)
    run = service.request_manual_run(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        profile_id="profile-tenant-a",
    )
    with Session(get_engine(radar_app)) as session:
        session.add(
            Notification(
                tenant_id="tenant-a",
                kind="radar_change",
                title="Radar update",
                target_url=f"/radar/runs/{run.id}",
                dedupe_key=f"radar-run:profile-tenant-a:{run.id}",
            )
        )
        session.commit()

    service.cancel_manual_run(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        run_id=run.id,
    )

    with Session(get_engine(radar_app)) as session:
        job = session.get(Job, run.root_job_id)
        notification = session.scalar(
            session.query(Notification).filter_by(tenant_id="tenant-a").statement
        )
        assert job is not None and job.status == "cancelled"
        assert notification is not None and notification.status == "archived"


def test_user_must_explicitly_accept_a_drifted_baseline(radar_app) -> None:
    import app.modules.radar.service as service
    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun

    _enable_radar(radar_app)
    _seed_profile(radar_app)
    with Session(get_engine(radar_app)) as session:
        session.add(
            RadarRun(
                id="drifted-run",
                tenant_id="tenant-a",
                profile_id="profile-tenant-a",
                root_job_id="drifted-job",
                requested_by="actor-a",
                status="succeeded",
                baseline_accepted=False,
                budget_json='{"pages":10}',
                result_summary_json='{"possible_baseline_drift":true}',
            )
        )
        session.commit()

    run = service.accept_run_baseline(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        run_id="drifted-run",
    )

    assert run.baseline_accepted is True
