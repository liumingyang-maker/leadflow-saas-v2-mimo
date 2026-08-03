from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session


def _fetch_result(*, url: str, text: str):
    from app.integrations.web.fetcher import FetchResult

    return FetchResult(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type="text/html",
        title="Acme Rival",
        text=text,
        content_hash=("a" if url.endswith("/") else "b") * 64,
        retrieved_at=datetime(2026, 8, 3, tzinfo=UTC),
        redirect_chain=(),
        observed_links=(),
    )


def _seed_run(app) -> tuple[object, object]:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot
    from app.modules.jobs.models import Job
    from app.modules.radar.models import CompetitorProfile, RadarRun

    with Session(get_engine(app)) as session:
        session.add(
            ProductKnowledgeSnapshot(
                id="snapshot-a",
                tenant_id="tenant-a",
                version="v1",
                product_name="Engine",
                summary="Motorcycle engine distributor product",
                content_hash="a" * 64,
                approved_by="actor-a",
            )
        )
        session.add(
            AcquisitionMission(
                id="mission-a",
                tenant_id="tenant-a",
                name="Mission",
                status="running",
                product_snapshot_id="snapshot-a",
                created_by="actor-a",
            )
        )
        profile = CompetitorProfile(
            id="profile-a",
            tenant_id="tenant-a",
            mission_id="mission-a",
            product_snapshot_id="snapshot-a",
            company_name="Acme Rival",
            canonical_domain="rival.example",
            official_url="https://rival.example/",
            tracking_config_json=(
                '{"seed_pages":[{"url":"https://rival.example/dealers","page_kind":"dealers"}]}'
            ),
        )
        job = Job(
            id="job-a",
            tenant_id="tenant-a",
            job_type="radar_scan",
            payload_json='{"run_id":"run-a"}',
        )
        run = RadarRun(
            id="run-a",
            tenant_id="tenant-a",
            profile_id="profile-a",
            root_job_id="job-a",
            requested_by="actor-a",
            active_key="active",
            budget_json='{"pages":10,"wall_seconds":300}',
        )
        session.add_all((profile, job, run))
        session.commit()
        session.refresh(job)
        session.expunge(job)
    return job, run


def test_manual_scan_preserves_static_snapshot_when_secondary_page_fails(
    monkeypatch,
    radar_app,
) -> None:
    import app.modules.radar.jobs as jobs
    from app.extensions import get_engine
    from app.integrations.web.fetcher import FetchError
    from app.modules.acquisition.models import Notification
    from app.modules.radar.models import RadarRun, RadarSnapshot

    job, _run = _seed_run(radar_app)

    class FakeFetcher:
        resolver = staticmethod(lambda _host: ["93.184.216.34"])

        def fetch(self, url: str):
            if url.endswith("/dealers"):
                raise FetchError("source_unreachable", "safe")
            return _fetch_result(url=url, text="Official motorcycle engine distributor")

        def close(self) -> None:
            return None

    monkeypatch.setattr(jobs.StaticFetcher, "from_app", lambda _app: FakeFetcher())

    summary = jobs.handle_radar_scan(radar_app, job, {"run_id": "run-a"})

    assert summary["run_status"] == "partial"
    assert summary["browser_jobs"] == 0
    with Session(get_engine(radar_app)) as session:
        run = session.get(RadarRun, "run-a")
        snapshots = list(session.query(RadarSnapshot).filter_by(run_id="run-a"))
        assert run is not None and run.status == "partial"
        assert len(snapshots) == 2
        assert {item.validation_status for item in snapshots} == {"valid", "unreachable"}
        notifications = list(
            session.query(Notification).filter_by(tenant_id="tenant-a", kind="radar_change")
        )
        assert len(notifications) == 1


def test_radar_scan_is_registered_in_the_validated_worker_registry() -> None:
    import app.modules.jobs.worker as worker

    assert worker._get_job_handler("radar_scan") is not None


def test_planning_failure_ends_run_and_closes_fetcher(monkeypatch, radar_app) -> None:
    import app.modules.radar.jobs as jobs
    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun

    job, _run = _seed_run(radar_app)

    class FakeFetcher:
        resolver = staticmethod(lambda _host: ["93.184.216.34"])
        closed = False

        def close(self) -> None:
            type(self).closed = True

    monkeypatch.setattr(jobs.StaticFetcher, "from_app", lambda _app: FakeFetcher())
    monkeypatch.setattr(
        jobs,
        "plan_radar_pages",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid plan")),
    )

    summary = jobs.handle_radar_scan(radar_app, job, {"run_id": "run-a"})

    assert summary["run_status"] == "failed"
    assert "planning_failed" in summary["reason_codes"]
    assert FakeFetcher.closed is True
    with Session(get_engine(radar_app)) as session:
        run = session.get(RadarRun, "run-a")
        assert run is not None and run.status == "failed"


def test_unsafe_final_url_ends_the_run_without_leaving_it_active(monkeypatch, radar_app) -> None:
    import app.modules.radar.jobs as jobs
    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun

    job, _run = _seed_run(radar_app)

    class FakeFetcher:
        resolver = staticmethod(lambda _host: ["93.184.216.34"])

        def fetch(self, url: str):
            result = _fetch_result(url=url, text="Unexpected redirect")
            return result.__class__(**{**result.__dict__, "final_url": "https://attacker.example/"})

        def close(self) -> None:
            return None

    monkeypatch.setattr(jobs.StaticFetcher, "from_app", lambda _app: FakeFetcher())

    summary = jobs.handle_radar_scan(radar_app, job, {"run_id": "run-a"})

    assert summary["run_status"] == "failed"
    assert "final_url_rejected" in summary["reason_codes"]
    with Session(get_engine(radar_app)) as session:
        run = session.get(RadarRun, "run-a")
        assert run is not None and run.status == "failed"


def test_identical_followup_run_uses_prior_snapshots_without_false_drift(
    monkeypatch, radar_app
) -> None:
    import json

    import app.modules.radar.jobs as jobs
    from app.extensions import get_engine
    from app.modules.jobs.models import Job
    from app.modules.radar.models import CompetitorProfile, RadarRun

    job_a, _run = _seed_run(radar_app)
    with Session(get_engine(radar_app)) as session:
        profile = session.get(CompetitorProfile, "profile-a")
        assert profile is not None
        profile.tracking_config_json = json.dumps(
            {
                "seed_pages": [
                    {"url": "https://rival.example/dealers", "page_kind": "dealers"},
                    {"url": "https://rival.example/products", "page_kind": "product"},
                ]
            }
        )
        session.commit()

    class FakeFetcher:
        resolver = staticmethod(lambda _host: ["93.184.216.34"])

        def fetch(self, url: str):
            return _fetch_result(url=url, text=f"Acme Rival content for {url}")

        def close(self) -> None:
            return None

    monkeypatch.setattr(jobs.StaticFetcher, "from_app", lambda _app: FakeFetcher())
    first = jobs.handle_radar_scan(radar_app, job_a, {"run_id": "run-a"})
    assert first["possible_baseline_drift"] is False
    assert first["notification"] is False
    with Session(get_engine(radar_app)) as session:
        session.add(
            Job(
                id="job-b",
                tenant_id="tenant-a",
                job_type="radar_scan",
                payload_json='{"run_id":"run-b"}',
            )
        )
        session.add(
            RadarRun(
                id="run-b",
                tenant_id="tenant-a",
                profile_id="profile-a",
                root_job_id="job-b",
                requested_by="actor-a",
                active_key="active",
                budget_json='{"pages":10,"wall_seconds":300}',
            )
        )
        session.commit()
        job_b = session.get(Job, "job-b")
        assert job_b is not None
        session.expunge(job_b)

    second = jobs.handle_radar_scan(radar_app, job_b, {"run_id": "run-b"})
    assert second["possible_baseline_drift"] is False
    assert second["notification"] is False
    with Session(get_engine(radar_app)) as session:
        run = session.get(RadarRun, "run-b")
        assert run is not None
        assert len(json.loads(run.result_summary_json)["pages"]) == 3


def test_drifted_run_is_not_selected_as_the_next_baseline(radar_app) -> None:
    import app.modules.radar.jobs as jobs
    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun

    _job, _run = _seed_run(radar_app)
    with Session(get_engine(radar_app)) as session:
        accepted = RadarRun(
            id="run-accepted",
            tenant_id="tenant-a",
            profile_id="profile-a",
            root_job_id="job-accepted",
            requested_by="actor-a",
            status="succeeded",
            baseline_accepted=True,
            budget_json='{"pages":10}',
        )
        drifted = RadarRun(
            id="run-drifted",
            tenant_id="tenant-a",
            profile_id="profile-a",
            root_job_id="job-drifted",
            requested_by="actor-a",
            status="succeeded",
            baseline_accepted=False,
            budget_json='{"pages":10}',
            result_summary_json='{"possible_baseline_drift":true}',
        )
        session.add_all((accepted, drifted))
        session.commit()

        previous = jobs._previous_accepted_run(
            session,
            tenant_id="tenant-a",
            profile_id="profile-a",
            current_run_id="run-drifted",
        )

    assert previous is not None and previous.id == "run-accepted"


def test_recovered_radar_job_can_resume_its_running_run(radar_app) -> None:
    import app.modules.radar.jobs as jobs

    job, _run = _seed_run(radar_app)
    first, _profile = jobs._start_run(radar_app, job=job, run_id="run-a")
    resumed, _profile = jobs._start_run(radar_app, job=job, run_id="run-a")

    assert first.status == "running"
    assert resumed.status == "running"


def test_terminal_radar_worker_error_releases_the_active_run(radar_app) -> None:
    import app.modules.radar.jobs as jobs
    from app.extensions import get_engine
    from app.modules.jobs.models import Job
    from app.modules.radar.models import RadarRun

    job, _run = _seed_run(radar_app)
    with Session(get_engine(radar_app)) as session:
        stored_job = session.get(Job, job.id)
        assert stored_job is not None
        stored_job.status = "failed"
        session.commit()

    jobs.finalize_radar_worker_failure(radar_app, job_id=job.id, tenant_id="tenant-a")

    with Session(get_engine(radar_app)) as session:
        run = session.get(RadarRun, "run-a")
        assert run is not None
        assert run.status == "failed"
        assert run.active_key is None


def test_cancellation_during_reconciliation_prevents_later_conversion(
    monkeypatch,
    radar_app,
) -> None:
    import app.modules.radar.jobs as jobs
    import app.modules.radar.service as service
    from app.core.capabilities import Capability
    from app.extensions import get_engine
    from app.modules.radar.models import RadarRun

    radar_app.config["CAPABILITIES"][Capability.COMPETITOR_RADAR] = True
    job, _run = _seed_run(radar_app)
    conversion_called = False

    class FakeFetcher:
        resolver = staticmethod(lambda _host: ["93.184.216.34"])

        def fetch(self, url: str):
            return _fetch_result(url=url, text="Official motorcycle engine distributor")

        def close(self) -> None:
            return None

    def cancel_during_reconciliation(app, *, run, profile):
        service.cancel_manual_run(
            app,
            tenant_id=run.tenant_id,
            actor_id=run.requested_by,
            run_id=run.id,
        )
        return {"signals": 0, "possible_baseline_drift": False, "notification": False}

    def unexpected_conversion(*_args, **_kwargs):
        nonlocal conversion_called
        conversion_called = True
        return {"relationships": 1, "automatic_candidates": 1, "confirmed": 1}

    monkeypatch.setattr(jobs.StaticFetcher, "from_app", lambda _app: FakeFetcher())
    monkeypatch.setattr(jobs, "_reconcile_change_signals", cancel_during_reconciliation)
    monkeypatch.setattr(jobs, "_resolve_relationships_and_candidates", unexpected_conversion)

    summary = jobs.handle_radar_scan(radar_app, job, {"run_id": "run-a"})

    assert summary["run_status"] == "cancelled"
    assert conversion_called is False
    with Session(get_engine(radar_app)) as session:
        run = session.get(RadarRun, "run-a")
        assert run is not None and run.status == "cancelled"
