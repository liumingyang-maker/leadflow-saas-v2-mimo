from __future__ import annotations

import pytest
from sqlalchemy.orm import Session


def _seed_mission(
    session: Session,
    *,
    tenant_id: str,
    mission_id: str,
    status: str = "running",
    snapshot_id: str | None = None,
) -> str:
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot

    snapshot_id = snapshot_id or f"snapshot-{mission_id}"
    session.add(
        ProductKnowledgeSnapshot(
            id=snapshot_id,
            tenant_id=tenant_id,
            version="v1",
            product_name=f"Product {mission_id}",
            summary="A product summary",
            content_hash="a" * 64,
            approved_by="owner-a",
        )
    )
    session.add(
        AcquisitionMission(
            id=mission_id,
            tenant_id=tenant_id,
            name=f"Mission {mission_id}",
            status=status,
            product_snapshot_id=snapshot_id,
            created_by="owner-a",
        )
    )
    return snapshot_id


def test_radar_repositories_scope_reads_and_writes_to_tenant(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import CompetitorProfile, RadarCompetitorSuggestion
    from app.modules.radar.repository import CompetitorProfileRepository, RadarSuggestionRepository

    with Session(get_engine(radar_app)) as session:
        snapshot_id = _seed_mission(session, tenant_id="tenant-a", mission_id="mission-a")
        _seed_mission(session, tenant_id="tenant-b", mission_id="mission-b")
        profile = CompetitorProfile(
            id="profile-a",
            tenant_id="tenant-a",
            mission_id="mission-a",
            product_snapshot_id=snapshot_id,
            company_name="Acme Rival",
            canonical_domain="rival.example",
            official_url="https://rival.example/",
        )
        suggestion = RadarCompetitorSuggestion(
            id="suggestion-a",
            tenant_id="tenant-a",
            mission_id="mission-a",
            company_name="Acme Rival",
            canonical_domain="rival.example",
            official_url="https://rival.example/",
            evidence_hash="a" * 64,
        )
        profiles = CompetitorProfileRepository(session)
        suggestions = RadarSuggestionRepository(session)
        profiles.add(profile, tenant_id="tenant-a")
        suggestions.add(suggestion, tenant_id="tenant-a")
        session.commit()

        assert profiles.get("profile-a", tenant_id="tenant-b") is None
        assert suggestions.get("suggestion-a", tenant_id="tenant-b") is None
        assert [item.id for item in profiles.list_for_tenant(tenant_id="tenant-a")] == ["profile-a"]
        assert [
            item.id for item in suggestions.list_for_mission("mission-a", tenant_id="tenant-a")
        ] == ["suggestion-a"]

        with pytest.raises(ValueError, match="tenant_id mismatch"):
            profiles.add(profile, tenant_id="tenant-b")


@pytest.mark.parametrize("status", ("draft", "completed", "failed", "cancelled"))
def test_policy_rejects_missions_that_are_not_active(status: str, radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.repository import MissionRepository
    from app.modules.radar.policies import RadarPolicyError, require_active_mission

    with Session(get_engine(radar_app)) as session:
        _seed_mission(session, tenant_id="tenant-a", mission_id="mission-a", status=status)
        session.commit()
        mission = MissionRepository(session).get("mission-a", tenant_id="tenant-a")
        assert mission is not None
        with pytest.raises(RadarPolicyError, match="active"):
            require_active_mission(mission)


@pytest.mark.parametrize("status", ("queued", "running", "paused"))
def test_policy_accepts_active_mission_statuses(status: str, radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.repository import MissionRepository
    from app.modules.radar.policies import require_active_mission

    with Session(get_engine(radar_app)) as session:
        _seed_mission(session, tenant_id="tenant-a", mission_id="mission-a", status=status)
        session.commit()
        mission = MissionRepository(session).get("mission-a", tenant_id="tenant-a")
        assert mission is not None
        assert require_active_mission(mission) is mission


def test_policy_rejects_product_snapshot_from_other_tenant_or_mission(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.repository import MissionRepository, ProductKnowledgeRepository
    from app.modules.radar.policies import RadarPolicyError, require_matching_product_snapshot

    with Session(get_engine(radar_app)) as session:
        _seed_mission(session, tenant_id="tenant-a", mission_id="mission-a")
        _seed_mission(session, tenant_id="tenant-a", mission_id="mission-b")
        _seed_mission(session, tenant_id="tenant-b", mission_id="mission-c")
        session.commit()
        missions = MissionRepository(session)
        snapshots = ProductKnowledgeRepository(session)
        mission_a = missions.get("mission-a", tenant_id="tenant-a")
        mission_b = missions.get("mission-b", tenant_id="tenant-a")
        foreign_snapshot = snapshots.get("snapshot-mission-c", tenant_id="tenant-b")
        assert mission_a is not None
        assert mission_b is not None
        assert foreign_snapshot is not None

        with pytest.raises(RadarPolicyError, match="Mission"):
            require_matching_product_snapshot(mission_a, foreign_snapshot)
        matching_b = snapshots.get(mission_b.product_snapshot_id, tenant_id="tenant-a")
        assert matching_b is not None
        with pytest.raises(RadarPolicyError, match="Mission"):
            require_matching_product_snapshot(mission_a, matching_b)


def test_policy_canonicalizes_public_urls_and_hashes_json_stably() -> None:
    from app.modules.radar.policies import canonical_json, canonical_public_url, evidence_hash

    def resolver(_host: str) -> list[str]:
        return ["93.184.216.34"]

    safe_url = canonical_public_url("HTTPS://Example.COM/about#ignored", resolver=resolver)

    assert safe_url.canonical_url == "https://example.com/about"
    assert safe_url.host == "example.com"
    assert canonical_json({"b": [2, 1], "a": "value"}) == '{"a":"value","b":[2,1]}'
    assert evidence_hash({"a": "value", "b": [2, 1]}) == evidence_hash({"b": [2, 1], "a": "value"})
