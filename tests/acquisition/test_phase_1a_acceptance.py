from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


def test_safe_event_keeps_operational_fields_and_redacts_sensitive_values():
    from app.core.logging import safe_event

    event = safe_event(
        "candidate.verified",
        tenant_id="tenant-very-private",
        mission_id="mission-1",
        provider="mimo",
        duration_ms=41,
        url="https://example.com/path?q=secret#fragment",
        API_KEY="must-not-appear",
        authorization="Bearer must-not-appear",
        html="<p>private body</p>",
        random_debug_value="drop-me",
    )

    assert event["event"] == "candidate.verified"
    assert event["tenant_ref"] != "tenant-very-private"
    assert len(event["tenant_ref"]) == 12
    assert event["url"] == "https://example.com/path"
    assert event["mission_id"] == "mission-1"
    assert event["duration_ms"] == 41
    serialized = json.dumps(event)
    assert "must-not-appear" not in serialized
    assert "private body" not in serialized
    assert "drop-me" not in serialized

    unsafe_event = safe_event("password=must-not-appear")
    assert unsafe_event["event"] == "application.log"
    assert "must-not-appear" not in json.dumps(unsafe_event)


def test_mimo_failure_notifies_once_and_recovery_is_audited(acquisition_app):
    from app.extensions import get_engine
    from app.modules.acquisition.jobs import (
        _provider_failure,
        _provider_success,
        reconcile_missions,
    )
    from app.modules.acquisition.models import Notification, ProviderStatus
    from app.modules.audit.models import AuditEvent

    for _ in range(4):
        _provider_failure(acquisition_app, "t1", "provider_unavailable")

    with Session(get_engine(acquisition_app)) as session:
        status = session.scalars(select(ProviderStatus)).one()
        assert status.status == "failed"
        assert status.consecutive_failures == 4
        assert session.scalar(select(func.count()).select_from(Notification)) == 1
        session.execute(delete(Notification))
        session.commit()

    reconcile_missions(acquisition_app, tenant_id="t1", now=datetime.now(UTC))
    with Session(get_engine(acquisition_app)) as session:
        assert session.scalar(select(func.count()).select_from(Notification)) == 1

    _provider_success(acquisition_app, "t1")

    with Session(get_engine(acquisition_app)) as session:
        status = session.scalars(select(ProviderStatus)).one()
        assert status.status == "healthy"
        assert status.consecutive_failures == 0
        recovery = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "provider.recovered")
        ).one()
        assert recovery.tenant_id == "t1"
        assert "provider_unavailable" not in recovery.safe_summary


def test_settings_explains_provider_status(acquisition_app, logged_in_client):
    from app.extensions import get_engine
    from app.modules.acquisition.models import ProviderStatus

    client, tenant_id = logged_in_client
    with Session(get_engine(acquisition_app)) as session:
        session.add(
            ProviderStatus(
                tenant_id=tenant_id,
                provider="mimo",
                status="degraded",
                consecutive_failures=2,
                error_code="provider_unavailable",
                last_checked_at=datetime(2026, 8, 2, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

    response = client.get("/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MiMo provider" in html
    assert "degraded" in html
    assert "2 consecutive failures" in html
    assert "provider_unavailable" in html


def test_manual_url_pipeline_works_when_mimo_is_disabled(acquisition_app, seed_acquisition_mission):
    from app.integrations.ai.contracts import ExtractedCompanyFacts
    from app.integrations.web.fetcher import FetchResult
    from app.modules.acquisition.service import process_manual_url

    acquisition_app.config["MIMO_BASE_URL"] = ""
    mission_id = seed_acquisition_mission()
    source_url = "https://manual.example/products"
    snapshot = FetchResult(
        requested_url=source_url,
        final_url=source_url,
        status_code=200,
        content_type="text/html",
        title="Manual Co",
        text="Motorcycle engine distributor in Mexico. Contact sales.",
        content_hash="a" * 64,
        retrieved_at=datetime.now(UTC),
        redirect_chain=(),
    )
    facts = ExtractedCompanyFacts(
        company_name="Manual Co",
        canonical_domain="manual.example",
        opportunity_country_code="MX",
        buyer_type="distributor",
        product_terms=["motorcycle engine"],
        contact_paths=["https://manual.example/contact"],
        observed_claims=[
            {
                "claim_id": "claim-1",
                "text": "Motorcycle engine distributor in Mexico",
                "source_url": source_url,
            }
        ],
    )
    fetcher = type("Fetcher", (), {"fetch": lambda self, _url: snapshot})()
    extractor = type("Extractor", (), {"extract": lambda self, _snapshot: facts})()

    candidate = process_manual_url(
        acquisition_app,
        tenant_id="t1",
        mission_id=mission_id,
        url=source_url,
        fetcher=fetcher,
        extractor=extractor,
    )

    assert candidate.source_channel == "manual_url"
    assert candidate.status == "eligible"
    assert candidate.priority_score is not None


def test_country_unknown_cannot_be_accepted_and_score_is_deterministic():
    from app.modules.acquisition.scoring import (
        EligibilityFacts,
        ScoreInput,
        evaluate_gate,
        score_candidate,
    )

    gate = evaluate_gate(
        EligibilityFacts(
            country_status="unknown",
            buyer_type_match=True,
            excluded_business=False,
            independent_identity=True,
            product_evidence=True,
            contact_path=True,
        )
    )
    score_input = ScoreInput(
        product_relevance=90,
        buyer_role=80,
        country_match=None,
        company_size=None,
        industry_match=None,
        direct_purchase=None,
        recent_activity=None,
        competitor_signal=None,
        signal_recency=None,
        identity_quality=None,
        source_trust=None,
        contactability=None,
        independent_evidence=None,
        data_recency=None,
    )

    assert gate.disposition == "needs_evidence"
    assert "country_unknown" in gate.reason_codes
    assert score_candidate(score_input) == score_candidate(score_input)
