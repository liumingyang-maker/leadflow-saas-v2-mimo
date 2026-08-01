from __future__ import annotations

from datetime import UTC, datetime

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
