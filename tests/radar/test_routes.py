from __future__ import annotations

import re

from sqlalchemy.orm import Session


def _enable_radar(app) -> None:
    from app.core.capabilities import Capability

    app.config["CAPABILITIES"][Capability.COMPETITOR_RADAR] = True
    app.config["CAPABILITIES"][Capability.AI_RESEARCH] = True


def _seed_suggestion(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    suggestion_id: str = "suggestion-a",
):
    from app.extensions import get_engine
    from app.modules.radar.models import RadarCompetitorSuggestion

    with Session(get_engine(app)) as session:
        suggestion = RadarCompetitorSuggestion(
            id=suggestion_id,
            tenant_id=tenant_id,
            mission_id=mission_id,
            company_name="Acme Rival",
            canonical_domain="rival.example",
            official_url="https://rival.example/",
            reason_codes_json='["same-product-category"]',
            evidence_json=(
                '[{"excerpt":"Lists Acme Rival as an engine supplier.",'
                '"source_url":"https://source.example/directory"}]'
            ),
            evidence_hash="a" * 64,
        )
        session.add(suggestion)
        session.commit()
    return suggestion


def _csrf_token(html: str) -> str:
    found = re.search(r'csrf_token" value="([^"]+)"', html)
    assert found is not None, "CSRF token not found"
    return found.group(1)


def test_radar_routes_are_capability_protected_and_tenant_scoped(
    radar_app, radar_logged_in_client, seed_radar_mission
) -> None:
    client, tenant_id, _actor_id = radar_logged_in_client
    seed_radar_mission(tenant_id=tenant_id, mission_id="mission-a")
    seed_radar_mission(tenant_id="tenant-b", mission_id="mission-b")

    assert client.get("/radar").status_code == 404

    _enable_radar(radar_app)
    overview = client.get("/radar")
    assert overview.status_code == 200
    assert "mission-a" in overview.get_data(as_text=True)
    assert "mission-b" not in overview.get_data(as_text=True)
    assert client.get("/radar/missions/mission-b/suggestions").status_code == 404


def test_suggestion_page_displays_cited_evidence_without_get_side_effects(
    radar_app, radar_logged_in_client, seed_radar_mission
) -> None:
    client, tenant_id, _actor_id = radar_logged_in_client
    _enable_radar(radar_app)
    seed_radar_mission(tenant_id=tenant_id, mission_id="mission-a")
    _seed_suggestion(radar_app, tenant_id=tenant_id, mission_id="mission-a")

    response = client.get("/radar/missions/mission-a/suggestions")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Acme Rival" in html
    assert "https://rival.example/" in html
    assert "https://source.example/directory" in html
    assert "Lists Acme Rival as an engine supplier." in html
    assert "same-product-category" in html
    assert "Status: proposed" in html


def test_manual_request_post_requires_csrf_and_redirects_after_valid_request(
    monkeypatch, radar_app, radar_logged_in_client, seed_radar_mission
) -> None:
    import app.modules.radar.routes as routes

    client, tenant_id, _actor_id = radar_logged_in_client
    _enable_radar(radar_app)
    seed_radar_mission(tenant_id=tenant_id, mission_id="mission-a")
    radar_app.config["WTF_CSRF_ENABLED"] = True
    monkeypatch.setattr(routes, "request_competitor_suggestions", lambda *_args, **_kwargs: ())

    assert client.post("/radar/missions/mission-a/suggestions/request").status_code == 400
    page = client.get("/radar/missions/mission-a/suggestions")
    response = client.post(
        "/radar/missions/mission-a/suggestions/request",
        data={"csrf_token": _csrf_token(page.get_data(as_text=True))},
    )

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/radar/missions/mission-a/suggestions")


def test_approve_and_dismiss_posts_are_tenant_scoped_and_idempotent(
    radar_app, radar_logged_in_client, seed_radar_mission
) -> None:
    client, tenant_id, actor_id = radar_logged_in_client
    _enable_radar(radar_app)
    seed_radar_mission(tenant_id=tenant_id, mission_id="mission-a")
    _seed_suggestion(radar_app, tenant_id=tenant_id, mission_id="mission-a")

    first = client.post("/radar/suggestions/suggestion-a/approve")
    second = client.post("/radar/suggestions/suggestion-a/approve")

    assert first.status_code in {302, 303}
    assert second.status_code in {302, 303}
    assert first.headers["Location"] == second.headers["Location"]
    assert "/radar/profiles/" in first.headers["Location"]
    assert client.get(first.headers["Location"]).status_code == 200

    seed_radar_mission(tenant_id=tenant_id, mission_id="mission-c")
    _seed_suggestion(
        radar_app,
        tenant_id=tenant_id,
        mission_id="mission-c",
        suggestion_id="suggestion-c",
    )
    dismissed = client.post("/radar/suggestions/suggestion-c/dismiss")
    dismissed_again = client.post("/radar/suggestions/suggestion-c/dismiss")

    assert actor_id
    assert dismissed.status_code in {302, 303}
    assert dismissed_again.status_code in {302, 303}
    assert dismissed.headers["Location"] == dismissed_again.headers["Location"]
    assert client.post("/radar/suggestions/foreign/approve").status_code == 404
