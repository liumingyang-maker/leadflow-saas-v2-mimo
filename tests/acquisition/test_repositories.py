from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session


def test_mission_input_has_only_three_required_business_fields():
    from app.modules.acquisition.contracts import MissionCreateInput

    value = MissionCreateInput(
        product_snapshot_id="p1",
        country_codes=["mx", "PE"],
        buyer_types=["distributor"],
    )
    assert value.country_codes == ["MX", "PE"]
    assert value.languages == {"MX": ["es"], "PE": ["es"]}
    assert value.max_candidates == 30
    assert value.max_verify == 10


def test_repository_never_reads_other_tenant(acquisition_app, seed_acquisition_mission):
    from app.extensions import get_engine
    from app.modules.acquisition.repository import MissionRepository

    mission_id = seed_acquisition_mission(tenant_id="t1")
    with Session(get_engine(acquisition_app)) as session:
        repo = MissionRepository(session)
        assert repo.get(mission_id, tenant_id="t1") is not None
        assert repo.get(mission_id, tenant_id="t2") is None


def test_candidate_repository_rejects_cross_tenant_write(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.repository import CandidateRepository

    with Session(get_engine(acquisition_app)) as session:
        repo = CandidateRepository(session)
        candidate = AcquisitionCandidate(tenant_id="t2", mission_id="m1", dedupe_key="d1")
        with pytest.raises(ValueError, match="tenant_id mismatch"):
            repo.add(candidate, tenant_id="t1")


def test_repository_requires_non_empty_tenant(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.repository import CandidateRepository

    with Session(get_engine(acquisition_app)) as session:
        with pytest.raises(ValueError, match="tenant_id is required"):
            CandidateRepository(session).get("c1", tenant_id=" ")


def test_candidate_status_map_is_tenant_scoped(acquisition_app, seed_acquisition_mission):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.repository import CandidateRepository

    own_mission = seed_acquisition_mission(tenant_id="t1", suffix="status-map-own")
    other_mission = seed_acquisition_mission(tenant_id="t2", suffix="status-map-other")
    with Session(get_engine(acquisition_app)) as session:
        own = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=own_mission,
            status="needs_evidence",
            dedupe_key="domain:status-map-own.example",
        )
        other = AcquisitionCandidate(
            tenant_id="t2",
            mission_id=other_mission,
            status="rejected",
            dedupe_key="domain:status-map-other.example",
        )
        session.add_all([own, other])
        session.commit()

        statuses = CandidateRepository(session).statuses_by_ids([own.id, other.id], tenant_id="t1")

    assert statuses == {own.id: "needs_evidence"}


def test_candidate_repository_atomically_marks_only_needs_evidence_candidate_verifying(
    acquisition_app, seed_acquisition_mission
):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.repository import CandidateRepository

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix="atomic-retry")
    with Session(get_engine(acquisition_app)) as session:
        candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=mission_id,
            status="needs_evidence",
            dedupe_key="domain:atomic-retry.example",
        )
        session.add(candidate)
        session.commit()
        candidate_id = candidate.id

        repo = CandidateRepository(session)
        assert repo.mark_verifying_if_needs_evidence(candidate_id, tenant_id="t1") is True
        assert repo.mark_verifying_if_needs_evidence(candidate_id, tenant_id="t1") is False
        assert repo.mark_verifying_if_needs_evidence(candidate_id, tenant_id="t2") is False
        session.commit()

    with Session(get_engine(acquisition_app)) as session:
        stored = session.get(AcquisitionCandidate, candidate_id)
        assert stored is not None
        assert stored.status == "verifying"


def test_mission_repository_selects_oldest_needs_evidence_mission(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        ProductKnowledgeSnapshot,
    )
    from app.modules.acquisition.repository import MissionRepository

    now = datetime.now(UTC)
    with Session(get_engine(acquisition_app)) as session:
        product = ProductKnowledgeSnapshot(
            id="repository-oldest-product",
            tenant_id="t1",
            version="v1",
            product_name="Engine",
            summary="Engine",
            content_hash="a" * 64,
            approved_by="u1",
        )
        older = AcquisitionMission(
            id="mission-a-older",
            tenant_id="t1",
            name="Older",
            product_snapshot_id=product.id,
            created_by="u1",
            created_at=now - timedelta(days=2),
        )
        newer = AcquisitionMission(
            id="mission-z-newer",
            tenant_id="t1",
            name="Newer",
            product_snapshot_id=product.id,
            created_by="u1",
            created_at=now - timedelta(days=1),
        )
        session.add_all([product, older, newer])
        session.flush()
        session.add_all(
            [
                AcquisitionCandidate(
                    tenant_id="t1",
                    mission_id=older.id,
                    status="needs_evidence",
                    dedupe_key="domain:repository-oldest.example",
                ),
                AcquisitionCandidate(
                    tenant_id="t1",
                    mission_id=newer.id,
                    status="needs_evidence",
                    dedupe_key="domain:repository-newer.example",
                ),
            ]
        )
        session.commit()

        mission_id = MissionRepository(session).oldest_id_with_candidate_status(
            "needs_evidence", tenant_id="t1"
        )

    assert mission_id == "mission-a-older"


def test_provider_status_records_failure_and_recovery(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.repository import ProviderStatusRepository

    now = datetime.now(UTC)
    with Session(get_engine(acquisition_app)) as session:
        repo = ProviderStatusRepository(session)
        failed = repo.record_failure("mimo", "timeout", now, tenant_id="t1")
        assert failed.consecutive_failures == 1
        assert failed.status == "degraded"
        recovered = repo.record_success("mimo", now, tenant_id="t1")
        assert recovered.consecutive_failures == 0
        assert recovered.status == "healthy"


def test_product_repository_returns_only_latest_version_per_product(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import ProductKnowledgeSnapshot
    from app.modules.acquisition.repository import ProductKnowledgeRepository

    with Session(get_engine(acquisition_app)) as session:
        repo = ProductKnowledgeRepository(session)
        repo.add(
            ProductKnowledgeSnapshot(
                tenant_id="t1",
                version="v1",
                product_name="Engine",
                summary="Old",
                content_hash="a" * 64,
                approved_by="u1",
            ),
            tenant_id="t1",
        )
        repo.add(
            ProductKnowledgeSnapshot(
                tenant_id="t1",
                version="v2",
                product_name="Engine",
                summary="New",
                content_hash="b" * 64,
                approved_by="u1",
            ),
            tenant_id="t1",
        )
        session.commit()
        latest = repo.list_latest(tenant_id="t1")
        assert [(item.product_name, item.version) for item in latest] == [("Engine", "v2")]
