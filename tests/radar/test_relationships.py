from __future__ import annotations

from sqlalchemy.orm import Session


def _resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def _seed_snapshot(app, *, excerpt: str, link_url: str, anchor_text: str = "Rider Mexico") -> None:
    from app.extensions import get_engine
    from app.modules.radar.models import CompetitorProfile, RadarRun, RadarSnapshot

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
                budget_json='{"pages":10,"wall_seconds":300}',
            )
        )
        session.add(
            RadarSnapshot(
                id="radar-snapshot-a",
                tenant_id="tenant-a",
                profile_id="profile-a",
                run_id="run-a",
                page_kind="dealers",
                requested_url="https://rival.example/dealers",
                canonical_url="https://rival.example/dealers",
                content_hash="a" * 64,
                facts_json=(
                    '{"facts":[{"key":"page.observed_link","value":{"url":"'
                    + link_url
                    + '","anchor_text":"'
                    + anchor_text
                    + '"}}],"reason_codes":[]}'
                ),
                excerpt=excerpt,
            )
        )
        session.commit()


def test_relationship_extractor_confirms_cited_official_distributor(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.relationships import extract_relationships

    _seed_snapshot(
        radar_app,
        excerpt="Rider Mexico is an authorized distributor for Acme Rival products.",
        link_url="https://rider.example/",
    )
    with Session(get_engine(radar_app)) as session:
        session.expire_on_commit = False
        relationships = extract_relationships(
            session,
            profile_id="profile-a",
            run_id="run-a",
            snapshot_id="radar-snapshot-a",
            resolver=_resolver,
        )
        session.commit()

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.relationship_type == "distributor"
    assert relationship.evidence_strength == "confirmed"
    assert relationship.canonical_domain == "rider.example"
    assert "official_source" in relationship.reason_codes_json


def test_partner_or_directory_like_target_never_becomes_confirmed(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.relationships import extract_relationships

    _seed_snapshot(
        radar_app,
        excerpt="Rider Mexico is our strategic partner.",
        link_url="https://directory.example/",
    )
    with Session(get_engine(radar_app)) as session:
        relationships = extract_relationships(
            session,
            profile_id="profile-a",
            run_id="run-a",
            snapshot_id="radar-snapshot-a",
            resolver=_resolver,
        )

    assert len(relationships) == 1
    assert relationships[0].relationship_type == "partner"
    assert relationships[0].evidence_strength != "confirmed"


def test_unrelated_outbound_link_cannot_borrow_a_page_wide_dealer_claim(radar_app) -> None:
    from app.extensions import get_engine
    from app.modules.radar.relationships import extract_relationships

    _seed_snapshot(
        radar_app,
        excerpt="Our dealer programme is open. Read the latest industry report.",
        link_url="https://media.example/report",
        anchor_text="Read the report",
    )
    with Session(get_engine(radar_app)) as session:
        relationships = extract_relationships(
            session,
            profile_id="profile-a",
            run_id="run-a",
            snapshot_id="radar-snapshot-a",
            resolver=_resolver,
        )

    assert len(relationships) == 1
    assert relationships[0].evidence_strength != "confirmed"
