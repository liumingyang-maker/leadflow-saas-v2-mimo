from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_candidate_and_evidence_are_tenant_owned(acquisition_app, seed_acquisition_mission):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate, CandidateEvidence

    mission_id = seed_acquisition_mission()
    with Session(get_engine(acquisition_app)) as session:
        candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=mission_id,
            company_name="Moto MX",
            dedupe_key="domain:moto.example",
        )
        session.add(candidate)
        session.flush()
        evidence = CandidateEvidence(
            tenant_id="t1",
            candidate_id=candidate.id,
            source_url="https://moto.example/about",
            canonical_url="https://moto.example/about",
            content_hash="a" * 64,
        )
        session.add(evidence)
        session.commit()
        assert candidate.status == "discovered"
        assert evidence.validation_status == "unverified"
        assert candidate.tenant_id == evidence.tenant_id == "t1"


def test_candidate_unique_per_mission_and_dedupe_key(acquisition_app, seed_acquisition_mission):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate

    mission_id = seed_acquisition_mission()
    with Session(get_engine(acquisition_app)) as session:
        for _ in range(2):
            session.add(
                AcquisitionCandidate(
                    tenant_id="t1",
                    mission_id=mission_id,
                    dedupe_key="domain:x.example",
                )
            )
        with pytest.raises(IntegrityError):
            session.commit()


def test_candidate_priority_range_is_enforced(acquisition_app, seed_acquisition_mission):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate

    mission_id = seed_acquisition_mission()
    with Session(get_engine(acquisition_app)) as session:
        session.add(
            AcquisitionCandidate(
                tenant_id="t1",
                mission_id=mission_id,
                priority_score=101,
                dedupe_key="domain:invalid.example",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
