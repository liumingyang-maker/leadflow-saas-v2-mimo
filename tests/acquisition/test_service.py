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


def _row_snapshot(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


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
                    channel_policy_json=json.dumps(
                        {"allowed_channels": ["manual_url"], "browser_research": False}
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


def _seed_manual_mission(app, *, mission_id: str = "manual-mission") -> str:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot
    from app.modules.acquisition.policies import canonical_json

    product_id = f"{mission_id}-product"
    with Session(get_engine(app)) as session:
        session.add(
            ProductKnowledgeSnapshot(
                id=product_id,
                tenant_id="t1",
                version="v1",
                product_name=f"Engine {mission_id}",
                summary="Motorcycle engine",
                facts_json=canonical_json([{"name": "Product", "value": "Engine"}]),
                content_hash="e" * 64,
                approved_by="u1",
            )
        )
        session.add(
            AcquisitionMission(
                id=mission_id,
                tenant_id="t1",
                name="Manual Mexico distributors",
                product_snapshot_id=product_id,
                target_profile_json=canonical_json(
                    {
                        "country_codes": ["MX"],
                        "buyer_types": ["distributor"],
                        "exclude_terms": [],
                    }
                ),
                channel_policy_json=canonical_json(
                    {"allowed_channels": ["manual_url"], "browser_research": False}
                ),
                created_by="u1",
            )
        )
        session.commit()
    return mission_id


def _fetch_result(
    *,
    requested_url: str,
    final_url: str | None = None,
    text: str,
    content_hash: str,
    detected_prompt_injection: bool = False,
):
    from app.integrations.web.fetcher import FetchResult

    return FetchResult(
        requested_url=requested_url,
        final_url=final_url or requested_url,
        status_code=200,
        content_type="text/html",
        title="Manual Co",
        text=text,
        content_hash=content_hash,
        retrieved_at=datetime.now(UTC),
        redirect_chain=(),
        detected_prompt_injection=detected_prompt_injection,
    )


def _generic_facts(
    source_url: str,
    *,
    claim_id: str = "mimo-product-evidence",
    buyer_type: str = "distributor",
    company_name: str = "Manual Co",
):
    from app.integrations.ai.contracts import ExtractedCompanyFacts

    return ExtractedCompanyFacts(
        company_name=company_name,
        canonical_domain="hallucinated.example",
        opportunity_country_code="MX",
        buyer_type=buyer_type,
        product_terms=[],
        contact_paths=["mailto:sales@manual.example"],
        observed_claims=[
            {
                "claim_id": claim_id,
                "text": "Motorcycle engine distributor in Mexico",
                "source_url": source_url,
            }
        ],
    )


def _manual_artifact_counts(app, mission_id: str) -> tuple[int, int, int]:
    from app.extensions import get_engine
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )

    with Session(get_engine(app)) as session:
        candidate_count = session.scalar(
            select(func.count())
            .select_from(AcquisitionCandidate)
            .where(AcquisitionCandidate.mission_id == mission_id)
        )
        evidence_count = session.scalar(
            select(func.count())
            .select_from(CandidateEvidence)
            .join(AcquisitionCandidate)
            .where(AcquisitionCandidate.mission_id == mission_id)
        )
        assessment_count = session.scalar(
            select(func.count())
            .select_from(CandidateAssessment)
            .join(AcquisitionCandidate)
            .where(AcquisitionCandidate.mission_id == mission_id)
        )
    return int(candidate_count or 0), int(evidence_count or 0), int(assessment_count or 0)


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
    from app.modules.acquisition.models import CandidateAssessment, CandidateEvidence
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
    assert candidate.source_provider == "manual"
    assert candidate.status == "eligible"
    assert candidate.priority_score is not None
    with Session(get_engine(acquisition_app)) as session:
        assessment = session.scalar(select(CandidateAssessment))
        evidence = session.scalar(select(CandidateEvidence))
        assert assessment is not None
        assert evidence is not None
        assert evidence.provider == "manual"
        assert assessment.model_provider == "mimo"
        assert assessment.model_id == acquisition_app.config["MIMO_MODEL"]
        assert assessment.prompt_version == "company-extract-v1"
        assert assessment.score_version == "priority-v3"


def test_manual_facts_need_no_mimo_and_are_idempotent(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app)
    source_url = "https://www.manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        final_url="https://manual.example/products",
        text="Manual Co is a motorcycle engine distributor in Mexico. "
        "Contact sales@manual.example.",
        content_hash="1" * 64,
    )

    class StaticFetcher:
        def fetch(self, url):
            assert url == source_url
            return snapshot

    value = ManualCompanyFactsInput(
        url=source_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="motorcycle engine distributor in Mexico",
        contact_path="sales@manual.example",
    )

    first = process_manual_facts(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        value=value,
        fetcher=StaticFetcher(),
    )
    second = process_manual_facts(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        value=value,
        fetcher=StaticFetcher(),
    )

    assert first.id == second.id
    assert second.status == "eligible"
    assert second.source_channel == "manual_url"
    assert second.source_provider == "manual"
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 1
        assessment = session.scalars(select(CandidateAssessment)).one()
        evidence = session.scalars(select(CandidateEvidence)).one()
        assert evidence.provider == "manual"
        assert assessment.model_provider == "manual"
        assert assessment.model_id == "human-confirmed-v1"
        assert assessment.prompt_version == "manual-facts-v1"
        assert assessment.score_version == "priority-v3"


@pytest.mark.parametrize("mode", ["ai_extract", "manual_facts"])
def test_cancelled_manual_mission_rejects_before_fetch(acquisition_app, mode: str):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.acquisition.service import (
        AcquisitionError,
        process_manual_facts,
        process_manual_url,
    )

    mission_id = _seed_manual_mission(acquisition_app, mission_id=f"cancelled-{mode}")
    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, mission_id)
        assert mission is not None
        mission.status = "cancelled"
        session.commit()

    calls: list[str] = []

    class Fetcher:
        def fetch(self, _url):
            calls.append("fetch")
            raise AssertionError("cancelled mission must not fetch")

    if mode == "ai_extract":
        extractor = type(
            "Extractor",
            (),
            {"extract": lambda self, _snapshot: calls.append("extract")},
        )()

        def operation():
            return process_manual_url(
                acquisition_app,
                tenant_id="t1",
                mission_id=mission_id,
                url="https://manual.example/products",
                fetcher=Fetcher(),
                extractor=extractor,
            )

    else:
        value = ManualCompanyFactsInput(
            url="https://manual.example/products",
            company_name="Manual Co",
            opportunity_country_code="MX",
            buyer_type="distributor",
            evidence_text="motorcycle engine distributor in Mexico",
            contact_path="sales@manual.example",
        )

        def operation():
            return process_manual_facts(
                acquisition_app,
                tenant_id="t1",
                mission_id=mission_id,
                value=value,
                fetcher=Fetcher(),
            )

    with pytest.raises(AcquisitionError) as raised:
        operation()

    assert type(raised.value).__name__ == "AcquisitionStateError"
    assert str(raised.value) == "manual URL acquisition is unavailable for cancelled mission"
    assert calls == []
    assert _manual_artifact_counts(acquisition_app, mission_id) == (0, 0, 0)


def test_manual_url_cancellation_race_writes_no_artifacts(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.acquisition.service import AcquisitionError, process_manual_url

    mission_id = _seed_manual_mission(acquisition_app, mission_id="manual-url-race")
    source_url = "https://manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="Motorcycle engine distributor in Mexico. Contact sales@manual.example.",
        content_hash="d" * 64,
    )
    facts = _generic_facts(source_url)
    calls: list[str] = []

    class CancellingFetcher:
        def fetch(self, _url):
            calls.append("fetch")
            with Session(get_engine(acquisition_app)) as session:
                mission = session.get(AcquisitionMission, mission_id)
                assert mission is not None
                mission.status = "cancelled"
                session.commit()
            return snapshot

    class Extractor:
        def extract(self, _snapshot):
            calls.append("extract")
            return facts

    with pytest.raises(AcquisitionError) as raised:
        process_manual_url(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            url=source_url,
            fetcher=CancellingFetcher(),
            extractor=Extractor(),
        )

    assert type(raised.value).__name__ == "AcquisitionStateError"
    assert str(raised.value) == "manual URL acquisition is unavailable for cancelled mission"
    assert calls == ["fetch", "extract"]
    assert _manual_artifact_counts(acquisition_app, mission_id) == (0, 0, 0)


def test_manual_facts_cancellation_race_writes_no_artifacts(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.acquisition.service import AcquisitionError, process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app, mission_id="manual-facts-race")
    source_url = "https://manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="Manual Co is a motorcycle engine distributor in Mexico. "
        "Contact sales@manual.example.",
        content_hash="f" * 64,
    )
    value = ManualCompanyFactsInput(
        url=source_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="motorcycle engine distributor in Mexico",
        contact_path="sales@manual.example",
    )
    calls: list[str] = []

    class CancellingFetcher:
        def fetch(self, _url):
            calls.append("fetch")
            with Session(get_engine(acquisition_app)) as session:
                mission = session.get(AcquisitionMission, mission_id)
                assert mission is not None
                mission.status = "cancelled"
                session.commit()
            return snapshot

    with pytest.raises(AcquisitionError) as raised:
        process_manual_facts(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            value=value,
            fetcher=CancellingFetcher(),
        )

    assert type(raised.value).__name__ == "AcquisitionStateError"
    assert str(raised.value) == "manual URL acquisition is unavailable for cancelled mission"
    assert calls == ["fetch"]
    assert _manual_artifact_counts(acquisition_app, mission_id) == (0, 0, 0)


def test_manual_facts_same_domain_contact_url_persists_each_snapshot_once(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import CandidateAssessment, CandidateEvidence
    from app.modules.acquisition.service import process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app)
    primary_url = "https://manual.example/products"
    contact_url = "https://manual.example/contact"
    snapshots = {
        primary_url: _fetch_result(
            requested_url=primary_url,
            final_url="https://www.manual.example/products",
            text="Manual Co is a motorcycle engine distributor in Mexico.",
            content_hash="2" * 64,
        ),
        contact_url: _fetch_result(
            requested_url=contact_url,
            final_url="https://manual.example/contact-us",
            text="Contact the Manual Co sales team.",
            content_hash="3" * 64,
        ),
    }
    calls: list[str] = []

    class StaticFetcher:
        def fetch(self, url):
            calls.append(url)
            return snapshots[url]

    value = ManualCompanyFactsInput(
        url=primary_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="motorcycle engine distributor in Mexico",
        contact_path=contact_url,
    )

    first = process_manual_facts(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        value=value,
        fetcher=StaticFetcher(),
    )
    second = process_manual_facts(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        value=value,
        fetcher=StaticFetcher(),
    )

    assert first.id == second.id
    assert calls == [primary_url, contact_url, primary_url, contact_url]
    with Session(get_engine(acquisition_app)) as session:
        evidence = list(session.scalars(select(CandidateEvidence)))
        assert len(evidence) == 2
        assert {item.source_url for item in evidence} == {primary_url, contact_url}
        supports = {item.canonical_url: json.loads(item.supports_json) for item in evidence}
        assert supports["https://www.manual.example/products"] == ["manual-product-evidence"]
        assert supports["https://manual.example/contact-us"] == []
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 1


def test_manual_facts_rejects_absent_evidence_before_writing(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app)
    source_url = "https://manual.example/products?private=query-secret"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="private page body that must not leak",
        content_hash="4" * 64,
    )
    value = ManualCompanyFactsInput(
        url=source_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="sentence absent from page",
        contact_path="sales@manual.example",
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()

    with pytest.raises(AcquisitionError) as raised:
        process_manual_facts(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            value=value,
            fetcher=fetcher,
        )

    message = str(raised.value)
    assert message == "manual company facts are not supported by website evidence"
    assert "query-secret" not in message
    assert "private page body" not in message
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 0


def test_manual_facts_rejects_cross_domain_contact_before_fetch(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app)
    primary_url = "https://manual.example/products?private=query-secret"
    snapshot = _fetch_result(
        requested_url=primary_url,
        text="Motorcycle engine distributor in Mexico. Private body secret.",
        content_hash="5" * 64,
    )
    calls: list[str] = []

    class StaticFetcher:
        def fetch(self, url):
            calls.append(url)
            return snapshot

    value = ManualCompanyFactsInput(
        url=primary_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="Motorcycle engine distributor in Mexico",
        contact_path="https://attacker.example/contact?secret=contact-query",
    )

    with pytest.raises(AcquisitionError) as raised:
        process_manual_facts(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            value=value,
            fetcher=StaticFetcher(),
        )

    assert calls == [primary_url]
    message = str(raised.value)
    assert message == "manual company facts are not supported by website evidence"
    assert "query-secret" not in message
    assert "contact-query" not in message
    assert "Private body secret" not in message
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 0


def test_manual_facts_rejects_contact_redirect_off_domain_before_writing(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app)
    primary_url = "https://manual.example/products?private=primary-query-secret"
    contact_url = "https://manual.example/contact?private=contact-query-secret"
    snapshots = {
        primary_url: _fetch_result(
            requested_url=primary_url,
            text="Motorcycle engine distributor in Mexico. Private primary body secret.",
            content_hash="9" * 64,
        ),
        contact_url: _fetch_result(
            requested_url=contact_url,
            final_url="https://attacker.example/contact?private=redirect-query-secret",
            text="Private redirected contact body secret.",
            content_hash="a" * 64,
        ),
    }
    calls: list[str] = []

    class StaticFetcher:
        def fetch(self, url):
            calls.append(url)
            return snapshots[url]

    value = ManualCompanyFactsInput(
        url=primary_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="Motorcycle engine distributor in Mexico",
        contact_path=contact_url,
    )

    with pytest.raises(AcquisitionError) as raised:
        process_manual_facts(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            value=value,
            fetcher=StaticFetcher(),
        )

    assert calls == [primary_url, contact_url]
    message = str(raised.value)
    assert message == "manual company facts are not supported by website evidence"
    assert len(message) <= 100
    assert "primary-query-secret" not in message
    assert "contact-query-secret" not in message
    assert "redirect-query-secret" not in message
    assert "Private" not in message
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 0


@pytest.mark.parametrize("injected_page", ["primary", "contact"])
def test_manual_facts_rejects_prompt_injection_before_writing(acquisition_app, injected_page):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, process_manual_facts

    mission_id = _seed_manual_mission(acquisition_app)
    primary_url = "https://manual.example/products?secret=primary-query"
    contact_url = "https://manual.example/contact?secret=contact-query"
    snapshots = {
        primary_url: _fetch_result(
            requested_url=primary_url,
            text="Motorcycle engine distributor in Mexico. Private primary body.",
            content_hash="6" * 64,
            detected_prompt_injection=injected_page == "primary",
        ),
        contact_url: _fetch_result(
            requested_url=contact_url,
            text="Private contact body.",
            content_hash="7" * 64,
            detected_prompt_injection=injected_page == "contact",
        ),
    }
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, url: snapshots[url]})()
    value = ManualCompanyFactsInput(
        url=primary_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="Motorcycle engine distributor in Mexico",
        contact_path=contact_url,
    )

    with pytest.raises(AcquisitionError) as raised:
        process_manual_facts(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            value=value,
            fetcher=fetcher,
        )

    message = str(raised.value)
    assert message == "prompt injection detected in website evidence"
    assert "primary-query" not in message
    assert "contact-query" not in message
    assert "Private" not in message
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 0


def test_manual_url_uses_primary_final_domain_and_rejects_unsupplied_claim(acquisition_app):
    from app.extensions import get_engine
    from app.integrations.ai.contracts import ExtractedCompanyFacts
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, process_manual_url

    mission_id = _seed_manual_mission(acquisition_app)
    source_url = "https://www.manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        final_url="https://manual.example/products",
        text="Manual Co engine distributor in Mexico.",
        content_hash="8" * 64,
    )
    facts = ExtractedCompanyFacts(
        company_name="Manual Co",
        canonical_domain="hallucinated.example",
        opportunity_country_code="MX",
        buyer_type="distributor",
        product_terms=["engine"],
        contact_paths=["mailto:sales@manual.example"],
        observed_claims=[
            {
                "claim_id": "claim-1",
                "text": "engine distributor",
                "source_url": snapshot.final_url,
            }
        ],
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()
    extractor = type("Extractor", (), {"extract": lambda self, _snapshot: facts})()

    candidate = process_manual_url(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        url=source_url,
        fetcher=fetcher,
        extractor=extractor,
    )
    assert candidate.domain == "manual.example"

    bad_mission_id = _seed_manual_mission(acquisition_app, mission_id="bad-claim-mission")
    bad_facts = facts.model_copy(deep=True)
    bad_facts.observed_claims[0].source_url = "https://other.example/claim?secret=value"
    bad_extractor = type("Extractor", (), {"extract": lambda self, _snapshot: bad_facts})()
    with pytest.raises(AcquisitionError) as raised:
        process_manual_url(
            acquisition_app,
            tenant_id="t1",
            mission_id=bad_mission_id,
            url=source_url,
            fetcher=fetcher,
            extractor=bad_extractor,
        )
    assert str(raised.value) == "observed claim cites an unsupplied source URL"
    assert "secret=value" not in str(raised.value)
    with Session(get_engine(acquisition_app)) as session:
        bad_candidates = session.scalar(
            select(func.count())
            .select_from(AcquisitionCandidate)
            .where(AcquisitionCandidate.mission_id == bad_mission_id)
        )
        assert bad_candidates == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(CandidateEvidence)
                .join(AcquisitionCandidate)
                .where(AcquisitionCandidate.mission_id == bad_mission_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(CandidateAssessment)
                .join(AcquisitionCandidate)
                .where(AcquisitionCandidate.mission_id == bad_mission_id)
            )
            == 0
        )


def test_same_assessment_version_rejects_changed_facts_and_rolls_back(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, process_manual_url

    mission_id = _seed_manual_mission(acquisition_app)
    source_url = "https://manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="Motorcycle engine distributor in Mexico. Contact sales@manual.example.",
        content_hash="b" * 64,
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()
    first_facts = _generic_facts(source_url, claim_id="claim-first")
    first_extractor = type("Extractor", (), {"extract": lambda self, _snapshot: first_facts})()

    candidate = process_manual_url(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        url=source_url,
        fetcher=fetcher,
        extractor=first_extractor,
    )
    with Session(get_engine(acquisition_app)) as session:
        stored_candidate = session.get(AcquisitionCandidate, candidate.id)
        evidence = session.scalars(select(CandidateEvidence)).one()
        assessment = session.scalars(select(CandidateAssessment)).one()
        assert stored_candidate is not None
        before = {
            "candidate": _row_snapshot(stored_candidate),
            "evidence": _row_snapshot(evidence),
            "assessment": _row_snapshot(assessment),
        }
        evidence_id = evidence.id
        assessment_id = assessment.id

    changed_facts = _generic_facts(
        source_url,
        claim_id="claim-private-secret",
        buyer_type="importer",
        company_name="Private Secret Company",
    )
    changed_extractor = type("Extractor", (), {"extract": lambda self, _snapshot: changed_facts})()
    with pytest.raises(AcquisitionError) as raised:
        process_manual_url(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            url=source_url,
            fetcher=fetcher,
            extractor=changed_extractor,
        )

    message = str(raised.value)
    assert message == "assessment conflicts with existing evidence version"
    assert len(message) <= 100
    assert "Private Secret Company" not in message
    assert "claim-private-secret" not in message
    with Session(get_engine(acquisition_app)) as session:
        stored_candidate = session.get(AcquisitionCandidate, candidate.id)
        evidence = session.get(CandidateEvidence, evidence_id)
        assessment = session.get(CandidateAssessment, assessment_id)
        assert stored_candidate is not None
        assert evidence is not None
        assert assessment is not None
        assert _row_snapshot(stored_candidate) == before["candidate"]
        assert _row_snapshot(evidence) == before["evidence"]
        assert _row_snapshot(assessment) == before["assessment"]
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 1


@pytest.mark.parametrize("order", ["mimo_then_manual", "manual_then_mimo"])
def test_cross_mode_reconciles_same_snapshot_claim_supports(acquisition_app, order):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import process_manual_facts, process_manual_url

    mission_id = _seed_manual_mission(acquisition_app)
    source_url = "https://manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="Motorcycle engine distributor in Mexico. Contact sales@manual.example.",
        content_hash="c" * 64,
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()
    mimo_facts = _generic_facts(source_url)
    extractor = type("Extractor", (), {"extract": lambda self, _snapshot: mimo_facts})()
    manual_value = ManualCompanyFactsInput(
        url=source_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="Motorcycle engine distributor in Mexico",
        contact_path="sales@manual.example",
    )

    def run_mimo():
        return process_manual_url(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            url=source_url,
            fetcher=fetcher,
            extractor=extractor,
        )

    def run_manual():
        return process_manual_facts(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            value=manual_value,
            fetcher=fetcher,
        )

    first, second = (
        (run_mimo(), run_manual()) if order == "mimo_then_manual" else (run_manual(), run_mimo())
    )

    assert first.id == second.id
    assert second.source_channel == "manual_url"
    assert second.source_provider == "manual"
    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, second.id)
        evidence = session.scalars(select(CandidateEvidence)).one()
        assessments = list(session.scalars(select(CandidateAssessment)))
        assert candidate is not None
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 1
        assert len(assessments) == 2
        assert evidence.provider == "manual"
        assert json.loads(evidence.supports_json) == [
            "manual-product-evidence",
            "mimo-product-evidence",
        ]
        current_claim_ids = {
            claim["claim_id"] for claim in json.loads(candidate.observed_facts_json)["claims"]
        }
        assert current_claim_ids <= set(json.loads(evidence.supports_json))
        by_provider = {item.model_provider: item for item in assessments}
        assert set(by_provider) == {"manual", "mimo"}
        assert by_provider["manual"].model_id == "human-confirmed-v1"
        assert by_provider["manual"].prompt_version == "manual-facts-v1"
        assert by_provider["mimo"].model_id == acquisition_app.config["MIMO_MODEL"]
        assert by_provider["mimo"].prompt_version == "company-extract-v1"


def test_existing_evidence_rejects_malformed_support_provenance(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import ManualCompanyFactsInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import (
        AcquisitionError,
        process_manual_facts,
        process_manual_url,
    )

    mission_id = _seed_manual_mission(acquisition_app)
    source_url = "https://manual.example/products"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="Motorcycle engine distributor in Mexico. Contact sales@manual.example.",
        content_hash="d" * 64,
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()
    manual_value = ManualCompanyFactsInput(
        url=source_url,
        company_name="Manual Co",
        opportunity_country_code="MX",
        buyer_type="distributor",
        evidence_text="Motorcycle engine distributor in Mexico",
        contact_path="sales@manual.example",
    )
    candidate = process_manual_facts(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        value=manual_value,
        fetcher=fetcher,
    )
    with Session(get_engine(acquisition_app)) as session:
        evidence = session.scalars(select(CandidateEvidence)).one()
        evidence.supports_json = "{}"
        session.commit()

    mimo_facts = _generic_facts(source_url)
    extractor = type("Extractor", (), {"extract": lambda self, _snapshot: mimo_facts})()
    with pytest.raises(AcquisitionError) as raised:
        process_manual_url(
            acquisition_app,
            tenant_id="t1",
            mission_id=mission_id,
            url=source_url,
            fetcher=fetcher,
            extractor=extractor,
        )

    assert str(raised.value) == "stored evidence support provenance is invalid"
    with Session(get_engine(acquisition_app)) as session:
        stored_candidate = session.get(AcquisitionCandidate, candidate.id)
        evidence = session.scalars(select(CandidateEvidence)).one()
        assert stored_candidate is not None
        assert evidence.supports_json == "{}"
        assert session.scalar(select(func.count()).select_from(AcquisitionCandidate)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 1
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 1


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
            "priority-v3",
        ]


def test_synchronous_assessment_uses_same_evidence_only_semantics(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import _assess_candidate_in_session

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="verifying",
        eligibility_code="",
        suffix="sync-provisional",
    )
    with Session(get_engine(acquisition_app)) as session:
        session.add(
            CandidateEvidence(
                tenant_id="t1",
                candidate_id=candidate_id,
                provider="mimo",
                source_type="web_search",
                trust_tier="D",
                source_url="https://motosync-provisional.example",
                canonical_url="https://motosync-provisional.example",
                title="Moto provisional",
                excerpt="Motorcycle parts distributor in Mexico",
                content_hash="d" * 64,
                validation_status="unverified",
            )
        )
        session.commit()

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
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assessment = session.scalar(
            select(CandidateAssessment).where(CandidateAssessment.candidate_id == candidate_id)
        )
        assert candidate is not None
        assert assessment is not None
        assert candidate.status == "needs_evidence"
        assert candidate.priority_band == "B"
        assert assessment.priority_mode == "evidence_only_provisional_v1"
        assert assessment.prompt_version == "evidence-only-v1"
        assert assessment.model_provider == "deterministic"


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


def test_country_override_persists_evidence_and_assesses_synchronously(
    acquisition_app, monkeypatch
):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import override_candidate_country
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app, status="needs_evidence", eligibility_code="country_unknown"
    )
    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        candidate.opportunity_country_code = ""
        candidate.country_resolution_status = "unknown"
        candidate.decision_reason_code = "country_unknown"
        candidate.observed_facts_json = json.dumps(
            {
                "buyer_type": "distributor",
                "product_terms": ["engine"],
                "claims": [{"claim_id": "product-evidence", "text": "Engine distributor"}],
            }
        )
        session.commit()

    monkeypatch.setattr(
        "app.modules.acquisition.service.create_and_enqueue",
        lambda *_args, **_kwargs: pytest.fail("country evidence must not use Redis"),
        raising=False,
    )
    evidence_text = "Official contact office for Mexico distributors."
    snapshot = _fetch_result(
        requested_url="https://moto1.example/contact?token=secret-query",
        final_url="https://moto1.example/contact",
        text=f"Company profile. {evidence_text} Call sales today.",
        content_hash="e" * 64,
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()
    candidate = override_candidate_country(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        candidate_id=candidate_id,
        value=CountryEvidenceInput(
            country_code="MX",
            source_url=snapshot.requested_url,
            evidence_text=evidence_text,
            reason_code="official_contact_page",
        ),
        fetcher=fetcher,
    )
    assert candidate.opportunity_country_code == "MX"
    assert candidate.country_resolution_status == "confirmed"
    assert candidate.eligibility_code == "eligible"
    assert candidate.status == "eligible"
    assert candidate.decision_reason_code == ""
    with Session(get_engine(acquisition_app)) as session:
        evidence = session.scalars(
            select(CandidateEvidence).where(CandidateEvidence.candidate_id == candidate_id)
        ).one()
        assessment = session.scalars(
            select(CandidateAssessment).where(CandidateAssessment.candidate_id == candidate_id)
        ).one()
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "candidate.country_overridden")
        )
        assert event is not None
        assert evidence.provider == "manual"
        assert evidence.source_type == "country_evidence"
        assert evidence.trust_tier == "A"
        assert evidence.source_url == snapshot.requested_url
        assert evidence.canonical_url == snapshot.final_url
        assert evidence.content_hash == snapshot.content_hash
        assert json.loads(evidence.supports_json) == ["country-evidence"]
        assert evidence.validation_status == "valid"
        assert assessment.score_version == "priority-v3"
        assert assessment.model_provider == "manual"
        assert assessment.model_id == "human-confirmed-v1"
        assert assessment.prompt_version == "country-evidence-v1"
        assert "MX" in event.safe_summary
        assert "official_contact_page" in event.safe_summary
        assert "secret-query" not in event.safe_summary
        assert evidence_text not in event.safe_summary


def test_country_override_reuses_identical_evidence_and_unions_supports(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.models import CandidateAssessment, CandidateEvidence
    from app.modules.acquisition.service import override_candidate_country

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="country_conflicting",
        suffix="country-dedupe",
    )
    source_url = "https://country-dedupe.example/contact"
    evidence_text = "Official Mexico office"
    snapshot = _fetch_result(
        requested_url=source_url,
        text=("Earlier page content. " * 260) + evidence_text,
        content_hash="d" * 64,
    )
    with Session(get_engine(acquisition_app)) as session:
        session.add_all(
            [
                CandidateEvidence(
                    tenant_id="t1",
                    candidate_id=candidate_id,
                    provider="manual",
                    source_type="manual_url",
                    trust_tier="E",
                    source_url=source_url,
                    canonical_url=snapshot.final_url,
                    title="Existing source",
                    excerpt="Earlier page content. " * 10,
                    retrieved_at=datetime(2020, 1, 1, tzinfo=UTC),
                    content_hash=snapshot.content_hash,
                    supports_json=json.dumps(["existing-claim"]),
                    validation_status="contradicted",
                ),
                CandidateEvidence(
                    tenant_id="t1",
                    candidate_id=candidate_id,
                    provider="mimo",
                    source_type="search_result",
                    trust_tier="A",
                    source_url="https://country-dedupe.example/old",
                    canonical_url="https://country-dedupe.example/old",
                    title="Contradicted source",
                    excerpt="This row must not affect scoring.",
                    retrieved_at=datetime(2020, 1, 1, tzinfo=UTC),
                    content_hash="f" * 64,
                    supports_json=json.dumps(["contradicted-claim"]),
                    validation_status="contradicted",
                ),
            ]
        )
        session.commit()

    candidate = override_candidate_country(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        candidate_id=candidate_id,
        value=CountryEvidenceInput(
            country_code="MX",
            source_url=source_url,
            evidence_text=evidence_text,
            reason_code="official_contact_page",
        ),
        fetcher=type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})(),
    )

    assert candidate.country_resolution_status == "confirmed"
    with Session(get_engine(acquisition_app)) as session:
        rows = list(
            session.scalars(
                select(CandidateEvidence).where(CandidateEvidence.candidate_id == candidate_id)
            )
        )
        assert len(rows) == 2
        current = next(item for item in rows if item.content_hash == snapshot.content_hash)
        contradicted = next(item for item in rows if item.content_hash == "f" * 64)
        assert current.provider == "manual"
        assert current.trust_tier == "A"
        assert current.validation_status == "valid"
        assert current.excerpt == evidence_text
        assert current.retrieved_at.replace(tzinfo=UTC) == snapshot.retrieved_at
        assert json.loads(current.supports_json) == ["country-evidence", "existing-claim"]
        assert contradicted.validation_status == "contradicted"
        assessment = session.scalars(
            select(CandidateAssessment).where(CandidateAssessment.candidate_id == candidate_id)
        ).one()
        assert json.loads(assessment.input_json)["independent_evidence"] == 50


@pytest.mark.parametrize("status", ["eligible", "accepted", "promoted", "rejected"])
def test_country_override_requires_candidate_that_needs_evidence(acquisition_app, status):
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.service import AcquisitionStateError, override_candidate_country

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status=status,
        eligibility_code="country_unknown",
    )

    fetch_calls: list[str] = []

    class NoFetch:
        def fetch(self, url):
            fetch_calls.append(url)
            raise AssertionError("invalid candidate state must not fetch")

    with pytest.raises(AcquisitionStateError, match="need evidence"):
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            value=CountryEvidenceInput(
                country_code="MX",
                source_url="https://moto1.example/contact",
                evidence_text="Official Mexico office",
                reason_code="official_contact_page",
            ),
            fetcher=NoFetch(),
        )
    assert fetch_calls == []


def test_country_override_cas_rejects_stale_needs_evidence_state(acquisition_app, monkeypatch):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.repository import CandidateRepository
    from app.modules.acquisition.service import AcquisitionStateError, override_candidate_country
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="country_unknown",
        suffix="override-cas",
    )
    decided_at = datetime(2026, 2, 2, tzinfo=UTC)
    original_get = CandidateRepository.get

    get_calls = 0

    def get_then_commit_human_decision(repository, value, *, tenant_id):
        nonlocal get_calls
        get_calls += 1
        candidate = original_get(repository, value, tenant_id=tenant_id)
        assert candidate is not None
        if get_calls == 1:
            return candidate
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
    source_url = "https://moto-override-cas.example/contact"
    evidence_text = "Official Mexico office"
    snapshot = _fetch_result(
        requested_url=source_url,
        text=evidence_text,
        content_hash="c" * 64,
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()

    with pytest.raises(AcquisitionStateError, match="need evidence"):
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            value=CountryEvidenceInput(
                country_code="MX",
                source_url=source_url,
                evidence_text=evidence_text,
                reason_code="official_contact_page",
            ),
            fetcher=fetcher,
        )

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


@pytest.mark.parametrize("failure", ["absent", "prompt_injection"])
def test_country_override_rejects_unsupported_page_without_writes(acquisition_app, failure):
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, override_candidate_country
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="country_unknown",
        suffix=f"country-{failure}",
    )
    source_url = "https://country-failure.example/contact?private=query-secret"
    snapshot = _fetch_result(
        requested_url=source_url,
        text="Private page body without the submitted sentence.",
        content_hash=("a" if failure == "absent" else "b") * 64,
        detected_prompt_injection=failure == "prompt_injection",
    )
    fetcher = type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})()
    value = CountryEvidenceInput(
        country_code="MX",
        source_url=source_url,
        evidence_text="Official Mexico office",
        reason_code="official_contact_page",
    )

    with pytest.raises(AcquisitionError) as raised:
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            value=value,
            fetcher=fetcher,
        )

    message = str(raised.value)
    assert "query-secret" not in message
    assert "Private page body" not in message
    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        assert candidate.status == "needs_evidence"
        assert candidate.eligibility_code == "country_unknown"
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_country_override_cross_tenant_rejects_before_fetch(acquisition_app):
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.service import AcquisitionError, override_candidate_country

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="country_unknown",
        suffix="country-private",
    )
    fetch_calls: list[str] = []
    value = CountryEvidenceInput(
        country_code="MX",
        source_url="https://private-country.example/contact",
        evidence_text="Official Mexico office",
        reason_code="official_contact_page",
    )
    fetcher = type(
        "StaticFetcher",
        (),
        {"fetch": lambda self, url: fetch_calls.append(url)},
    )()

    with pytest.raises(AcquisitionError, match="not found"):
        override_candidate_country(
            acquisition_app,
            tenant_id="other-tenant",
            actor_id="other-user",
            candidate_id=candidate_id,
            value=value,
            fetcher=fetcher,
        )
    assert fetch_calls == []


def test_country_override_rolls_back_when_synchronous_assessment_fails(
    acquisition_app, monkeypatch
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.contracts import CountryEvidenceInput
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        CandidateAssessment,
        CandidateEvidence,
    )
    from app.modules.acquisition.service import AcquisitionError, override_candidate_country
    from app.modules.audit.models import AuditEvent

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="country_unknown",
        suffix="country-assessment-rollback",
    )
    source_url = "https://country-rollback.example/contact"
    evidence_text = "Official Mexico office"
    snapshot = _fetch_result(
        requested_url=source_url,
        text=evidence_text,
        content_hash="r" * 64,
    )

    def fail_assessment(*_args, **_kwargs):
        raise AcquisitionError("forced assessment failure")

    monkeypatch.setattr(
        "app.modules.acquisition.service._assess_candidate_in_session",
        fail_assessment,
    )
    with pytest.raises(AcquisitionError, match="forced assessment failure"):
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            value=CountryEvidenceInput(
                country_code="MX",
                source_url=source_url,
                evidence_text=evidence_text,
                reason_code="official_contact_page",
            ),
            fetcher=type("StaticFetcher", (), {"fetch": lambda self, _url: snapshot})(),
        )

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        assert candidate.status == "needs_evidence"
        assert candidate.eligibility_code == "country_unknown"
        assert session.scalar(select(func.count()).select_from(CandidateEvidence)) == 0
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 0
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


def test_retry_reopens_failed_mission_and_reconcile_can_complete_it(
    acquisition_app, monkeypatch
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.jobs import reconcile_missions
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        Notification,
    )
    from app.modules.acquisition.service import retry_candidate_verification
    from app.modules.audit.models import AuditEvent
    from app.modules.jobs.models import Job

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="missing_contact_path",
        suffix="retry-reopen",
    )
    failed_finished_at = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, "m1")
        assert mission is not None
        mission.status = "failed"
        mission.finished_at = failed_finished_at
        session.add(
            Notification(
                id="retry-failed-notification",
                tenant_id="t1",
                kind="mission_failed",
                title="Acquisition mission failed",
                body="Mexico dealers: 0 usable candidates",
                target_url="/acquisition/missions/m1",
                status="unread",
                dedupe_key="mission-terminal:m1:failed",
            )
        )
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        session.commit()

    def persist_retry_job(_app, **kwargs):
        with Session(get_engine(acquisition_app)) as session:
            job = Job(
                tenant_id=kwargs["tenant_id"],
                job_type=kwargs["job_type"],
                status="queued",
                payload_json=json.dumps(kwargs["payload"], sort_keys=True),
            )
            session.add(job)
            session.commit()
            return type("QueuedJob", (), {"id": job.id})()

    monkeypatch.setattr(
        "app.modules.acquisition.service.create_and_enqueue",
        persist_retry_job,
    )

    result = retry_candidate_verification(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        candidate_id=candidate_id,
    )

    assert result.candidate_id == candidate_id
    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        mission = session.get(AcquisitionMission, "m1")
        failed_notification = session.get(Notification, "retry-failed-notification")
        retry_job = session.scalar(
            select(Job).where(Job.job_type == "website_verify", Job.tenant_id == "t1")
        )
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "acquisition_candidate.verification_retried"
            )
        )
        assert candidate is not None
        assert candidate.status == "verifying"
        assert mission is not None
        assert mission.status == "running"
        assert mission.finished_at is None
        assert failed_notification is not None
        assert failed_notification.status == "archived"
        assert failed_notification.read_at is not None
        assert retry_job is not None
        assert json.loads(retry_job.payload_json) == {"candidate_id": candidate_id}
        assert audit is not None
        assert audit.actor_user_id == "u1"

        retry_job.status = "succeeded"
        retry_job.finished_at = datetime.now(UTC)
        candidate.status = "eligible"
        candidate.eligibility_code = "eligible"
        session.add(
            Job(
                tenant_id="t1",
                job_type="candidate_assess",
                status="succeeded",
                payload_json=json.dumps({"candidate_id": candidate_id}),
                finished_at=datetime.now(UTC),
            )
        )
        session.commit()

    assert (
        reconcile_missions(
            acquisition_app,
            tenant_id="t1",
            now=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        )
        == 1
    )

    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, "m1")
        failed_notification = session.get(Notification, "retry-failed-notification")
        completion = session.scalar(
            select(Notification).where(
                Notification.tenant_id == "t1",
                Notification.dedupe_key == "mission-terminal:m1:completed",
            )
        )
        assert mission is not None
        assert mission.status == "completed"
        assert failed_notification is not None
        assert failed_notification.status == "archived"
        assert completion is not None
        assert completion.kind == "mission_completed"
        assert completion.status == "unread"
        assert completion.body == "Mexico dealers: 1 usable candidates"


def test_retry_does_not_demote_completed_mission_with_usable_candidate(
    acquisition_app, monkeypatch
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate, AcquisitionMission
    from app.modules.acquisition.service import retry_candidate_verification
    from app.modules.jobs.models import Job

    retry_candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status="needs_evidence",
        eligibility_code="missing_contact_path",
        suffix="retry-completed",
    )
    completed_at = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, "m1")
        assert mission is not None
        mission.status = "completed"
        mission.finished_at = completed_at
        session.add(
            AcquisitionCandidate(
                tenant_id="t1",
                mission_id="m1",
                status="eligible",
                eligibility_code="eligible",
                dedupe_key="domain:retry-completed-usable.example",
            )
        )
        session.commit()

    def persist_retry_job(_app, **kwargs):
        with Session(get_engine(acquisition_app)) as session:
            job = Job(
                tenant_id=kwargs["tenant_id"],
                job_type=kwargs["job_type"],
                payload_json=json.dumps(kwargs["payload"]),
            )
            session.add(job)
            session.commit()
            return type("QueuedJob", (), {"id": job.id})()

    monkeypatch.setattr(
        "app.modules.acquisition.service.create_and_enqueue",
        persist_retry_job,
    )

    retry_candidate_verification(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        candidate_id=retry_candidate_id,
    )

    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, "m1")
        retry_candidate = session.get(AcquisitionCandidate, retry_candidate_id)
        assert mission is not None
        assert mission.status == "completed"
        assert mission.finished_at == completed_at.replace(tzinfo=None)
        assert retry_candidate is not None
        assert retry_candidate.status == "verifying"
