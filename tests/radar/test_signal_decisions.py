from __future__ import annotations

import re

from sqlalchemy.orm import Session


def _seed_signal(app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import (
        CompetitorProfile,
        RadarChangeSignal,
        RadarRun,
        RadarSnapshot,
    )

    with Session(get_engine(app)) as session:
        session.add(
            CompetitorProfile(
                id="profile-a",
                tenant_id="tenant-a",
                mission_id="mission-a",
                product_snapshot_id="snapshot-a",
                company_name="Acme Rival",
                canonical_domain="rival.example",
                official_url="https://rival.example/",
            )
        )
        session.add(
            RadarRun(
                id="run-a",
                tenant_id="tenant-a",
                profile_id="profile-a",
                root_job_id="job-a",
                requested_by="actor-a",
                status="succeeded",
                budget_json='{"pages":10}',
            )
        )
        session.add(
            RadarSnapshot(
                id="snapshot-a",
                tenant_id="tenant-a",
                profile_id="profile-a",
                run_id="run-a",
                page_kind="home",
                requested_url="https://rival.example/",
                canonical_url="https://rival.example/",
                content_hash="a" * 64,
                facts_json='{"facts":[]}',
                excerpt="",
            )
        )
        session.add(
            RadarChangeSignal(
                id="signal-a",
                tenant_id="tenant-a",
                profile_id="profile-a",
                run_id="run-a",
                current_snapshot_id="snapshot-a",
                change_type="other",
                materiality="material",
                detector_version="radar-diff-v1",
            )
        )
        session.commit()


def test_signal_decision_is_tenant_scoped_and_idempotent(radar_app) -> None:
    from app.core.capabilities import Capability
    from app.modules.radar.service import decide_change_signal

    radar_app.config["CAPABILITIES"][Capability.COMPETITOR_RADAR] = True
    _seed_signal(radar_app)
    first = decide_change_signal(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        signal_id="signal-a",
        action="acknowledge",
    )
    second = decide_change_signal(
        radar_app,
        tenant_id="tenant-a",
        actor_id="actor-b",
        signal_id="signal-a",
        action="dismiss",
    )

    assert first.status == "acknowledged"
    assert second.status == "acknowledged"
    assert second.decided_by == "actor-a"


def test_signal_decision_route_requires_csrf_and_records_action(
    radar_app,
    radar_logged_in_client,
    seed_radar_mission,
) -> None:
    from app.core.capabilities import Capability
    from app.extensions import get_engine
    from app.modules.radar.models import (
        CompetitorProfile,
        RadarChangeSignal,
        RadarRun,
        RadarSnapshot,
    )

    client, tenant_id, _actor_id = radar_logged_in_client
    radar_app.config["CAPABILITIES"][Capability.COMPETITOR_RADAR] = True
    radar_app.config["WTF_CSRF_ENABLED"] = True
    seed_radar_mission(tenant_id=tenant_id, mission_id="mission-a")
    with Session(get_engine(radar_app)) as session:
        session.add(
            CompetitorProfile(
                id="profile-route",
                tenant_id=tenant_id,
                mission_id="mission-a",
                product_snapshot_id="snapshot-mission-a",
                company_name="Acme Rival",
                canonical_domain="rival.example",
                official_url="https://rival.example/",
            )
        )
        session.add(
            RadarRun(
                id="run-route",
                tenant_id=tenant_id,
                profile_id="profile-route",
                root_job_id="job-route",
                requested_by="actor-a",
                status="succeeded",
                budget_json='{"pages":10}',
            )
        )
        session.add(
            RadarSnapshot(
                id="snapshot-route",
                tenant_id=tenant_id,
                profile_id="profile-route",
                run_id="run-route",
                page_kind="home",
                requested_url="https://rival.example/",
                canonical_url="https://rival.example/",
                content_hash="b" * 64,
                facts_json='{"facts":[]}',
                excerpt="",
            )
        )
        session.add(
            RadarChangeSignal(
                id="signal-route",
                tenant_id=tenant_id,
                profile_id="profile-route",
                run_id="run-route",
                current_snapshot_id="snapshot-route",
                change_type="other",
                materiality="material",
                detector_version="radar-diff-v1",
            )
        )
        session.commit()

    endpoint = "/radar/signals/signal-route/decision"
    assert client.post(endpoint, data={"action": "acknowledge"}).status_code == 400
    page = client.get("/radar/runs/run-route").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert token is not None
    response = client.post(
        endpoint,
        data={"action": "acknowledge", "csrf_token": token.group(1)},
    )

    assert response.status_code in {302, 303}
    with Session(get_engine(radar_app)) as session:
        signal = session.get(RadarChangeSignal, "signal-route")
        assert signal is not None and signal.status == "acknowledged"
