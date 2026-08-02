from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session


def _assessment_snapshot(assessment):
    from app.modules.acquisition.models import CandidateAssessment

    return {
        column.name: getattr(assessment, column.name)
        for column in CandidateAssessment.__table__.columns
    }


def _seed_mission_and_candidate(
    app, *, status: str, eligibility_code: str, suffix: str = "1"
) -> str:
    from app.extensions import get_engine
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        ProductKnowledgeSnapshot,
    )

    with Session(get_engine(app)) as session:
        if session.get(ProductKnowledgeSnapshot, "p1") is None:
            session.add(
                ProductKnowledgeSnapshot(
                    id="p1",
                    tenant_id="t1",
                    version="v1",
                    product_name="Engine",
                    summary="Motorcycle engine",
                    facts_json='[{"name":"Product","value":"Engine"}]',
                    content_hash="a" * 64,
                    approved_by="u1",
                )
            )
            session.add(
                AcquisitionMission(
                    id="m1",
                    tenant_id="t1",
                    name="Mexico dealers",
                    product_snapshot_id="p1",
                    target_profile_json=json.dumps(
                        {
                            "country_codes": ["MX"],
                            "buyer_types": ["distributor"],
                            "exclude_terms": [],
                        }
                    ),
                    created_by="u1",
                )
            )
        candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id="m1",
            status=status,
            eligibility_code=eligibility_code,
            company_name=f"Moto {suffix}",
            domain=f"moto{suffix}.example",
            website=f"https://moto{suffix}.example",
            opportunity_country_code="MX",
            country_resolution_status="confirmed",
            contact_json=json.dumps({"email": f"sales{suffix}@moto.example"}),
            decision_reason_code=eligibility_code if status == "rejected" else "",
            decided_at=datetime.now(UTC) if status == "rejected" else None,
            decided_by="u1" if status == "rejected" else "",
            dedupe_key=f"domain:moto{suffix}.example",
        )
        session.add(candidate)
        session.commit()
        return candidate.id


def _manual_url_inputs():
    from app.integrations.ai.contracts import ExtractedCompanyFacts
    from app.integrations.web.fetcher import FetchResult

    snapshot = FetchResult(
        requested_url="https://manual.example/products",
        final_url="https://manual.example/products",
        status_code=200,
        content_type="text/html",
        title="Manual Co",
        text="Engine distributor. Contact sales@manual.example",
        content_hash="c" * 64,
        retrieved_at=datetime.now(UTC),
        redirect_chain=(),
    )
    facts = ExtractedCompanyFacts(
        company_name="Manual Co",
        canonical_domain="manual.example",
        opportunity_country_code="MX",
        buyer_type="distributor",
        product_terms=["engine"],
        contact_paths=["mailto:sales@manual.example"],
        observed_claims=[
            {
                "claim_id": "claim-1",
                "text": "Engine distributor",
                "source_url": "https://manual.example/products",
            }
        ],
    )
    fetcher = type("Fetcher", (), {"fetch": lambda self, url: snapshot})()
    extractor = type("Extractor", (), {"extract": lambda self, value: facts})()
    return snapshot.requested_url, fetcher, extractor


def test_country_unknown_cannot_be_accepted(acquisition_app):
    from app.modules.acquisition.service import AcquisitionError, review_candidate

    candidate_id = _seed_mission_and_candidate(
        acquisition_app, status="needs_evidence", eligibility_code="country_unknown"
    )
    with pytest.raises(AcquisitionError, match="country evidence"):
        review_candidate(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            action="accept",
            reason_code="",
            note="",
        )


def test_promote_is_idempotent(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.service import promote_candidate
    from app.modules.leads.models import Company, Lead

    candidate_id = _seed_mission_and_candidate(
        acquisition_app, status="eligible", eligibility_code="eligible"
    )
    first = promote_candidate(
        acquisition_app, tenant_id="t1", actor_id="u1", candidate_id=candidate_id
    )
    second = promote_candidate(
        acquisition_app, tenant_id="t1", actor_id="u1", candidate_id=candidate_id
    )
    assert first.lead_id == second.lead_id
    assert first.company_id == second.company_id
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(Lead)) == 1
        assert session.scalar(select(func.count()).select_from(Company)) == 1


def test_accept_reviews_and_promotes_in_one_service_call(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.service import review_candidate
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app, status="eligible", eligibility_code="eligible"
    )
    candidate = review_candidate(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        candidate_id=candidate_id,
        action="accept",
        reason_code="",
        note="good fit",
    )
    assert candidate.status == "promoted"
    with Session(get_engine(acquisition_app)) as session:
        stored = session.get(AcquisitionCandidate, candidate_id)
        assert stored is not None and stored.promoted_lead_id
        actions = set(session.scalars(select(AuditEvent.action)))
        assert {"candidate.accepted", "candidate.promoted"} <= actions


def test_five_same_rejections_create_suggestion(acquisition_app):
    from app.modules.acquisition.service import summarize_feedback

    for index in range(5):
        _seed_mission_and_candidate(
            acquisition_app,
            status="rejected",
            eligibility_code="wrong_buyer_type",
            suffix=str(index),
        )
    suggestion = summarize_feedback(acquisition_app, tenant_id="t1", mission_id="m1")
    assert suggestion is not None
    assert suggestion.suggestion_type == "add_exclusion"
    assert suggestion.sample_size >= 5
    assert suggestion.status == "proposed"


def test_product_snapshots_are_append_only_versioned(acquisition_app):
    from app.modules.acquisition.service import create_product_snapshot

    first = create_product_snapshot(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        product_name="Engine",
        summary="Motorcycle engine",
        facts=[{"name": "displacement", "value": "150cc"}],
        prohibited_claims=["Zero emissions", "zero emissions"],
    )
    second = create_product_snapshot(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        product_name="Engine",
        summary="Updated motorcycle engine",
        facts=[{"name": "displacement", "value": "150cc"}],
        prohibited_claims=["Zero emissions"],
    )
    assert (first.version, second.version) == ("v1", "v2")
    assert first.id != second.id
    assert json.loads(first.prohibited_claims_json) == ["Zero emissions"]


def test_create_mission_uses_validated_defaults(acquisition_app):
    from app.modules.acquisition.contracts import MissionCreateInput
    from app.modules.acquisition.service import create_mission, create_product_snapshot

    product = create_product_snapshot(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        product_name="Engine",
        summary="Motorcycle engine",
        facts=[{"name": "category", "value": "engine"}],
        prohibited_claims=[],
    )
    mission = create_mission(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        value=MissionCreateInput(
            product_snapshot_id=product.id,
            country_codes=["MX"],
            buyer_types=["distributor"],
        ),
    )
    assert mission.status == "draft"
    assert json.loads(mission.target_profile_json)["languages"] == {"MX": ["es"]}
    assert json.loads(mission.channel_policy_json)["browser_research"] is False


def test_manual_url_still_fetches_extracts_and_assesses(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import CandidateAssessment
    from app.modules.acquisition.service import process_manual_url

    _seed_mission_and_candidate(
        acquisition_app, status="eligible", eligibility_code="eligible", suffix="seed"
    )
    url, fetcher, extractor = _manual_url_inputs()
    candidate = process_manual_url(
        acquisition_app,
        tenant_id="t1",
        mission_id="m1",
        url=url,
        fetcher=fetcher,
        extractor=extractor,
    )
    assert candidate.source_channel == "manual_url"
    assert candidate.status == "eligible"
    assert candidate.priority_score is not None
    with Session(get_engine(acquisition_app)) as session:
        assessment = session.scalar(select(CandidateAssessment))
        assert assessment is not None
        assert assessment.score_version == "priority-v2"


def test_current_assessment_preserves_historical_priority_v1_row(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        CandidateAssessment,
    )
    from app.modules.acquisition.policies import canonical_json
    from app.modules.acquisition.service import _assess_candidate_in_session

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="eligible",
        eligibility_code="eligible",
        suffix="priority-history",
    )
    bundle_hash = hashlib.sha256(canonical_json([]).encode("utf-8")).hexdigest()
    created_at = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
    historical_json = canonical_json({"priority_score": 91, "priority_band": "S"})

    with Session(get_engine(acquisition_app)) as session:
        historical = CandidateAssessment(
            tenant_id="t1",
            candidate_id=candidate_id,
            evidence_bundle_hash=bundle_hash,
            policy_version="eligibility-v1",
            score_version="priority-v1",
            prompt_version="company-extract-v1",
            model_provider="mimo",
            model_id="mimo-v2.5",
            input_json=canonical_json({"historical": True}),
            hard_gate_json=canonical_json({"disposition": "eligible"}),
            score_breakdown_json=historical_json,
            signal_coverage=100,
            priority_mode="full_v1",
            explanation="Historical priority-v1 assessment",
            created_at=created_at,
        )
        session.add(historical)
        session.commit()
        historical_id = historical.id
        before = _assessment_snapshot(historical)

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        mission = session.get(AcquisitionMission, "m1")
        assert candidate is not None
        assert mission is not None
        _assess_candidate_in_session(
            session,
            app=acquisition_app,
            candidate=candidate,
            mission=mission,
            tenant_id="t1",
        )
        session.commit()

    with Session(get_engine(acquisition_app)) as session:
        assessments = list(
            session.scalars(
                select(CandidateAssessment)
                .where(CandidateAssessment.candidate_id == candidate_id)
                .order_by(CandidateAssessment.score_version)
            )
        )
        historical = session.get(CandidateAssessment, historical_id)
        assert historical is not None
        assert _assessment_snapshot(historical) == before
        assert [assessment.score_version for assessment in assessments] == [
            "priority-v1",
            "priority-v2",
        ]


@pytest.mark.parametrize("status", ["accepted", "promoted", "rejected"])
def test_manual_url_reassessment_preserves_human_decision_and_refreshes_score(
    acquisition_app, status
):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.service import process_manual_url

    _seed_mission_and_candidate(
        acquisition_app,
        status="eligible",
        eligibility_code="eligible",
        suffix=f"sync-seed-{status}",
    )
    url, fetcher, extractor = _manual_url_inputs()
    candidate = process_manual_url(
        acquisition_app,
        tenant_id="t1",
        mission_id="m1",
        url=url,
        fetcher=fetcher,
        extractor=extractor,
    )
    candidate_id = candidate.id

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        candidate.status = status
        candidate.eligibility_code = "human-terminal"
        candidate.decision_reason_code = f"human-{status}"
        candidate.decided_by = f"reviewer-{status}"
        candidate.decided_at = datetime(2026, 3, 1, tzinfo=UTC)
        candidate.priority_score = None
        candidate.priority_band = ""
        candidate.signal_coverage = 0
        session.commit()

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        expected_decision = (
            candidate.status,
            candidate.eligibility_code,
            candidate.decision_reason_code,
            candidate.decided_by,
            candidate.decided_at,
        )

    reassessed = process_manual_url(
        acquisition_app,
        tenant_id="t1",
        mission_id="m1",
        url=url,
        fetcher=fetcher,
        extractor=extractor,
    )

    assert reassessed.id == candidate_id
    assert (
        reassessed.status,
        reassessed.eligibility_code,
        reassessed.decision_reason_code,
        reassessed.decided_by,
        reassessed.decided_at,
    ) == expected_decision
    assert reassessed.priority_score is not None
    assert reassessed.priority_band
    assert reassessed.signal_coverage > 0


def test_assessment_cas_preserves_human_decision_when_orm_state_is_stale(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate, AcquisitionMission
    from app.modules.acquisition.service import _assess_candidate_in_session

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="eligible",
        eligibility_code="eligible",
        suffix="assessment-cas",
    )
    decided_at = datetime(2026, 2, 1, tzinfo=UTC)

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        mission = session.get(AcquisitionMission, "m1")
        assert candidate is not None
        assert mission is not None
        session.execute(
            update(AcquisitionCandidate)
            .where(
                AcquisitionCandidate.id == candidate_id,
                AcquisitionCandidate.tenant_id == "t1",
            )
            .values(
                status="accepted",
                eligibility_code="human-terminal",
                decision_reason_code="human-accepted",
                decided_by="human-reviewer",
                decided_at=decided_at,
            ),
            execution_options={"synchronize_session": False},
        )
        assert candidate.status == "eligible"

        _assess_candidate_in_session(
            session,
            app=acquisition_app,
            candidate=candidate,
            mission=mission,
            tenant_id="t1",
        )
        session.commit()

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        assert (
            candidate.status,
            candidate.eligibility_code,
            candidate.decision_reason_code,
            candidate.decided_by,
            candidate.decided_at,
        ) == (
            "accepted",
            "human-terminal",
            "human-accepted",
            "human-reviewer",
            decided_at.replace(tzinfo=None),
        )


def test_apply_suggestion_does_not_mutate_historical_mission(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.acquisition.service import apply_suggestion, summarize_feedback

    for index in range(5):
        _seed_mission_and_candidate(
            acquisition_app,
            status="rejected",
            eligibility_code="wrong_buyer_type",
            suffix=str(index),
        )
    suggestion = summarize_feedback(acquisition_app, tenant_id="t1", mission_id="m1")
    assert suggestion is not None
    with Session(get_engine(acquisition_app)) as session:
        before = session.get(AcquisitionMission, "m1").target_profile_json
    first = apply_suggestion(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        suggestion_id=suggestion.id,
    )
    second = apply_suggestion(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        suggestion_id=suggestion.id,
    )
    assert first == second
    with Session(get_engine(acquisition_app)) as session:
        assert session.get(AcquisitionMission, "m1").target_profile_json == before


def test_rejected_candidate_cannot_be_promoted(acquisition_app):
    from app.modules.acquisition.service import AcquisitionError, promote_candidate

    candidate_id = _seed_mission_and_candidate(
        acquisition_app, status="rejected", eligibility_code="wrong_buyer_type"
    )
    with pytest.raises(AcquisitionError, match="cannot be promoted"):
        promote_candidate(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
        )


def test_country_override_is_audited_and_requeues_assessment(acquisition_app, monkeypatch):
    from app.extensions import get_engine
    from app.modules.acquisition.service import override_candidate_country
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app, status="needs_evidence", eligibility_code="country_unknown"
    )
    queued: list[dict] = []
    monkeypatch.setattr(
        "app.modules.acquisition.service.create_and_enqueue",
        lambda _app, **kwargs: queued.append(kwargs),
    )
    candidate = override_candidate_country(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        candidate_id=candidate_id,
        country_code="MX",
        source_url="https://moto1.example/contact",
        reason_code="official_contact_page",
    )
    assert candidate.country_resolution_status == "confirmed"
    assert candidate.status == "verifying"
    assert queued[0]["payload"] == {"candidate_id": candidate_id}
    with Session(get_engine(acquisition_app)) as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "candidate.country_overridden")
        )
        assert event is not None


@pytest.mark.parametrize("status", ["eligible", "accepted", "promoted", "rejected"])
def test_country_override_requires_candidate_that_needs_evidence(acquisition_app, status):
    from app.modules.acquisition.service import AcquisitionError, override_candidate_country

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status=status,
        eligibility_code="country_unknown",
    )

    with pytest.raises(AcquisitionError, match="need evidence"):
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            country_code="MX",
            source_url="https://moto1.example/contact",
            reason_code="official_contact_page",
        )


def test_country_override_cas_rejects_stale_needs_evidence_state(
    acquisition_app, monkeypatch
):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.repository import CandidateRepository
    from app.modules.acquisition.service import AcquisitionError, override_candidate_country
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="country_unknown",
        suffix="override-cas",
    )
    decided_at = datetime(2026, 2, 2, tzinfo=UTC)
    original_get = CandidateRepository.get

    def get_then_commit_human_decision(repository, value, *, tenant_id):
        candidate = original_get(repository, value, tenant_id=tenant_id)
        assert candidate is not None
        repository.session.execute(
            update(AcquisitionCandidate)
            .where(
                AcquisitionCandidate.id == value,
                AcquisitionCandidate.tenant_id == tenant_id,
            )
            .values(
                status="accepted",
                eligibility_code="human-terminal",
                opportunity_country_code="CA",
                country_resolution_status="confirmed",
                decision_reason_code="human-accepted",
                decided_by="human-reviewer",
                decided_at=decided_at,
            ),
            execution_options={"synchronize_session": False},
        )
        repository.session.commit()
        assert candidate.status == "needs_evidence"
        return candidate

    monkeypatch.setattr(CandidateRepository, "get", get_then_commit_human_decision)
    queued: list[dict] = []
    monkeypatch.setattr(
        "app.modules.acquisition.service.create_and_enqueue",
        lambda _app, **kwargs: queued.append(kwargs),
    )

    with pytest.raises(AcquisitionError, match="need evidence"):
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            country_code="MX",
            source_url="https://moto-override-cas.example/contact",
            reason_code="official_contact_page",
        )

    assert queued == []
    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        assert (
            candidate.status,
            candidate.eligibility_code,
            candidate.opportunity_country_code,
            candidate.country_resolution_status,
            candidate.decision_reason_code,
            candidate.decided_by,
            candidate.decided_at,
        ) == (
            "accepted",
            "human-terminal",
            "CA",
            "confirmed",
            "human-accepted",
            "human-reviewer",
            decided_at.replace(tzinfo=None),
        )
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_unknown_provider_cost_is_not_recorded_as_zero(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.acquisition.service import record_mission_cost

    _seed_mission_and_candidate(acquisition_app, status="eligible", eligibility_code="eligible")
    record_mission_cost(
        acquisition_app,
        tenant_id="t1",
        mission_id="m1",
        provider="mimo",
        requests=1,
        tokens=None,
        pages=None,
        estimated_cost=None,
        duration_ms=120,
    )
    with Session(get_engine(acquisition_app)) as session:
        summary = json.loads(session.get(AcquisitionMission, "m1").cost_summary_json)
    mimo = summary["providers"]["mimo"]
    assert mimo["requests"] == 1
    assert mimo["duration_ms"] == 120
    assert mimo["estimated_cost"] is None
