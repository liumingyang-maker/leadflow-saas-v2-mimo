from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "candidate-research-test-secret-key")
    monkeypatch.setenv("TENANT_SECRET_KEY", "candidate-research-test-tenant-key")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "candidate-research-test-outreach-key")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Research Co"):
    from app.modules.accounts.models import Tenant, TenantMembership, User

    with Session(engine) as session:
        tenant = Tenant(company_name=company, status="active", plan="basic")
        user = User(
            email=email,
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.commit()
        tenant_id = tenant.id
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["tenant_id"] = tenant_id
        sess["user_id"] = user_id
        sess["tenant_email"] = email
    return client, tenant_id, user_id


def _enable_fake_ai(app) -> None:
    from app.modules.ai.service import save_provider_settings

    save_provider_settings(
        app,
        provider="fake",
        enabled=True,
        base_url="",
        model="fake-ai",
        api_key="",
        timeout_seconds=25,
        max_output_tokens=800,
    )


def _enable_tenant_ai(app, *, tenant_id: str, credits: int = 100) -> None:
    from app.modules.ai.service import save_tenant_ai_settings

    save_tenant_ai_settings(
        app,
        tenant_id=tenant_id,
        enabled=True,
        monthly_included_credits=credits,
    )


def _confirmed_product_profile(engine, *, tenant_id: str) -> str:
    from app.modules.onboarding.models import TenantProductProfile

    profile_json = {
        "product_keywords_en": ["insulated bottle", "drinkware"],
        "target_industries": ["Retail"],
        "buyer_types": ["Importer", "Distributor"],
        "target_countries": ["United States", "Germany"],
        "search_keywords": ["insulated bottle importer"],
    }
    with Session(engine) as session:
        profile = TenantProductProfile(
            tenant_id=tenant_id,
            raw_company_intro="Bottle factory",
            raw_products="Insulated bottles",
            extracted_profile_json=json.dumps(profile_json),
            status="confirmed",
            confirmed_at=datetime.now(UTC),
        )
        session.add(profile)
        session.commit()
        return profile.id


def _candidate(engine, *, tenant_id: str, profile_id: str, website: str = "https://north.example"):
    from app.modules.jobs.target_models import TargetCustomerCandidate, TargetCustomerDiscoveryRun

    with Session(engine) as session:
        run = TargetCustomerDiscoveryRun(
            tenant_id=tenant_id,
            product_profile_id=profile_id,
            filters_json="{}",
            generated_plan_json="{}",
            status="matched",
            requested_count=1,
            generated_count=1,
            credits_estimated=0,
            credits_charged=0,
        )
        session.add(run)
        session.flush()
        candidate = TargetCustomerCandidate(
            tenant_id=tenant_id,
            run_id=run.id,
            company_name="Northstar Outdoor Supply",
            website=website,
            country="United States",
            industry="Outdoor retail",
            buyer_type="Distributor",
            source_channel="advanced_web_search",
            match_reason=(
                "Search snippet suggests outdoor retail categories. Contact test@example.com "
                "or +1 415 555 1212 should not be stored."
            ),
            confidence_score=78,
            raw_data_json=json.dumps(
                {
                    "source_provider": "brave",
                    "suggested_next_action": "Review catalog fit before outreach.",
                    "unverified": True,
                }
            ),
        )
        session.add(candidate)
        session.commit()
        return candidate.id


def test_candidate_detail_route_requires_login(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    with client.session_transaction() as sess:
        sess.clear()

    response = client.get(f"/collection/candidates/{candidate_id}")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_candidate_detail_blocks_cross_tenant_access(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _client_a, tenant_a, _user_a = _tenant_client(app, engine, email="a@example.com")
    client_b, _tenant_b, _user_b = _tenant_client(app, engine, email="b@example.com")
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_a)
    candidate_id = _candidate(engine, tenant_id=tenant_a, profile_id=profile_id)

    response = client_b.get(f"/collection/candidates/{candidate_id}")
    research = client_b.post(f"/collection/candidates/{candidate_id}/research")

    assert response.status_code == 404
    assert research.status_code == 404


def test_ai_disabled_blocks_provider_call_and_writes_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when AI is disabled")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/research")

    from app.modules.ai.models import AIUsageLedger

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "AI 功能暂未开启" in html
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.feature_name == "candidate_company_research"
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0


def test_quota_block_prevents_provider_call_and_charges_zero(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id, credits=0)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when quota is blocked")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/research")

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "额度不足" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "blocked_quota"
    assert ledger.credits_charged == 0


def test_successful_research_writes_sanitized_report_and_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    response = client.post(f"/collection/candidates/{candidate_id}/research")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateResearchReport
    from app.modules.outreach.models import OutreachMessage

    assert response.status_code in {302, 303}
    detail = client.get(f"/collection/candidates/{candidate_id}")
    html = detail.get_data(as_text=True)
    assert "AI 深度背调" in html
    assert "未验证" in html
    assert "系统不会自动发送邮件" in html
    assert "开发信切入角度" in html
    assert "test@example.com" not in html
    assert "415 555" not in html
    with Session(engine) as session:
        report = session.scalar(
            select(CandidateResearchReport).where(CandidateResearchReport.tenant_id == tenant_id)
        )
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        outreach_count = session.scalar(select(func.count(OutreachMessage.id)))
    assert report is not None
    assert report.status == "completed"
    assert report.ai_usage_ledger_id == ledger.id
    assert report.provider == "fake"
    assert report.search_provider == "brave"
    assert report.fit_score >= 0
    assert report.confidence_score >= 0
    stored = json.dumps(
        {
            "summary": report.summary,
            "sources": report.sources_json,
            "buyer": report.buyer_signals_json,
            "risks": report.risk_signals_json,
        },
        ensure_ascii=False,
    )
    assert "test@example.com" not in stored
    assert "415 555" not in stored
    assert "full prompt" not in report.__table__.columns
    assert ledger is not None
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert outreach_count == 0


def test_candidate_without_domain_creates_low_confidence_report(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id, website="")

    response = client.post(f"/collection/candidates/{candidate_id}/research")

    from app.modules.jobs.target_models import CandidateResearchReport

    assert response.status_code in {302, 303}
    with Session(engine) as session:
        report = session.scalar(
            select(CandidateResearchReport).where(CandidateResearchReport.tenant_id == tenant_id)
        )
    assert report is not None
    assert report.company_domain == ""
    assert report.confidence_score <= 45
    assert "缺少官网" in report.risk_signals_json


def test_provider_failure_shows_safe_error_and_charges_zero(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    from app.integrations.ai.base import AIGenerationResult

    def fail_generate(*_args, **_kwargs):
        return AIGenerationResult(
            success=False,
            text="",
            provider="fake",
            model="fake-ai",
            error_code="provider_error",
        )

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/research")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateResearchReport

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        report = session.scalar(
            select(CandidateResearchReport).where(CandidateResearchReport.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.credits_charged == 0
    assert report is not None
    assert report.status == "failed"
