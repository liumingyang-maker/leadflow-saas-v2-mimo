from __future__ import annotations

import pytest
from sqlalchemy.orm import Session


def _seed_relationship(
    app,
    *,
    relationship_type: str = "distributor",
    strength: str = "confirmed",
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot
    from app.modules.radar.models import (
        CompetitorProfile,
        RadarRelationship,
        RadarRun,
        RadarSnapshot,
    )

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
                budget_json='{"pages":10,"wall_seconds":300}',
            )
        )
        session.add(
            RadarSnapshot(
                id="snapshot-radar-a",
                tenant_id="tenant-a",
                profile_id="profile-a",
                run_id="run-a",
                page_kind="dealers",
                requested_url="https://rival.example/dealers",
                canonical_url="https://rival.example/dealers",
                content_hash="b" * 64,
                facts_json="{}",
                excerpt="Rider Mexico is an authorized distributor.",
            )
        )
        session.add(
            RadarRelationship(
                id="relationship-a",
                tenant_id="tenant-a",
                profile_id="profile-a",
                run_id="run-a",
                source_snapshot_id="snapshot-radar-a",
                company_name="Rider Mexico",
                canonical_domain="rider.example",
                official_url="https://rider.example/",
                relationship_type=relationship_type,
                evidence_strength=strength,
                reason_codes_json='["official_source","outbound_company_url"]',
                evidence_json=(
                    '[{"source_url":"https://rival.example/dealers",'
                    '"outbound_url":"https://rider.example/",'
                    '"excerpt":"Rider Mexico is an authorized distributor."}]'
                ),
            )
        )
        session.commit()


def test_acquisition_boundary_creates_review_only_candidate_from_confirmed_distributor(
    acquisition_app,
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import CandidateEvidence
    from app.modules.acquisition.service import create_candidate_from_radar_relationship

    _seed_relationship(acquisition_app)
    candidate = create_candidate_from_radar_relationship(
        acquisition_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        mission_id="mission-a",
        relationship_id="relationship-a",
        expected_domain="rider.example",
    )

    assert candidate.status == "needs_evidence"
    assert candidate.source_channel == "competitor_radar"
    assert candidate.domain == "rider.example"
    with Session(get_engine(acquisition_app)) as session:
        evidence = session.query(CandidateEvidence).filter_by(candidate_id=candidate.id).one()
        assert evidence.trust_tier == "B"
        assert evidence.source_type == "competitor_dealer_network"


@pytest.mark.parametrize(
    "relationship_type,strength",
    (("partner", "confirmed"), ("dealer", "likely")),
)
def test_acquisition_boundary_rejects_nonconvertible_radar_relationships(
    acquisition_app, relationship_type: str, strength: str
) -> None:
    from app.modules.acquisition.service import (
        AcquisitionStateError,
        create_candidate_from_radar_relationship,
    )

    _seed_relationship(acquisition_app, relationship_type=relationship_type, strength=strength)
    with pytest.raises(AcquisitionStateError):
        create_candidate_from_radar_relationship(
            acquisition_app,
            tenant_id="tenant-a",
            actor_id="actor-a",
            mission_id="mission-a",
            relationship_id="relationship-a",
            expected_domain="rider.example",
        )


def test_acquisition_boundary_rejects_a_relationship_from_a_drifted_run(acquisition_app) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.service import (
        AcquisitionStateError,
        create_candidate_from_radar_relationship,
    )
    from app.modules.radar.models import RadarRun

    _seed_relationship(acquisition_app)
    with Session(get_engine(acquisition_app)) as session:
        run = session.get(RadarRun, "run-a")
        assert run is not None
        run.result_summary_json = '{"possible_baseline_drift":true}'
        session.commit()

    with pytest.raises(AcquisitionStateError, match="baseline drift"):
        create_candidate_from_radar_relationship(
            acquisition_app,
            tenant_id="tenant-a",
            actor_id="actor-a",
            mission_id="mission-a",
            relationship_id="relationship-a",
            expected_domain="rider.example",
        )


def test_converting_an_already_converted_relationship_is_idempotent(acquisition_app) -> None:
    from app.modules.acquisition.service import create_candidate_from_radar_relationship

    _seed_relationship(acquisition_app)
    first = create_candidate_from_radar_relationship(
        acquisition_app,
        tenant_id="tenant-a",
        actor_id="actor-a",
        mission_id="mission-a",
        relationship_id="relationship-a",
        expected_domain="rider.example",
    )
    second = create_candidate_from_radar_relationship(
        acquisition_app,
        tenant_id="tenant-a",
        actor_id="actor-b",
        mission_id="mission-a",
        relationship_id="relationship-a",
        expected_domain="rider.example",
    )

    assert second.id == first.id
