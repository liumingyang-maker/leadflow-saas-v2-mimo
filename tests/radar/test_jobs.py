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


def test_radar_scan_is_registered_in_the_validated_worker_registry() -> None:
    import app.modules.jobs.worker as worker

    assert worker._get_job_handler("radar_scan") is not None
