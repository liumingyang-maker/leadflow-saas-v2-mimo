from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "advanced-search-test-secret-key")
    monkeypatch.setenv("TENANT_SECRET_KEY", "advanced-search-test-tenant-key")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "advanced-search-test-outreach-key")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Search Co"):
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


def _enable_tenant_ai(app, *, tenant_id: str, credits: int = 100) -> None:
    from app.modules.ai.service import save_tenant_ai_settings

    save_tenant_ai_settings(
        app,
        tenant_id=tenant_id,
        enabled=True,
        monthly_included_credits=credits,
    )


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


def _enable_fake_acquisition(app, *, daily_cap: int = 100) -> None:
    from app.modules.acquisition.service import save_acquisition_settings

    save_acquisition_settings(
        app,
        provider="fake",
        enabled=True,
        api_key="",
        daily_spend_cap_cents=daily_cap,
        query_limit_per_run=3,
        result_limit_per_run=10,
        timeout_seconds=10,
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


def _run_advanced_search(client):
    return client.post(
        "/collection/channels/advanced-web-search/run",
        data={
            "country": "United States",
            "buyer_type": "Importer",
            "industry": "Retail",
            "result_count": "5",
        },
    )


def test_advanced_channel_unconfigured_by_default(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    response = client.get("/collection")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动网页搜索" in html
    assert "需要管理员配置" in html
    assert "高级自动网页搜索尚未配置" in html


def test_disabled_tenant_cannot_call_advanced_search_provider(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    _enable_fake_acquisition(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_search(*_args, **_kwargs):
        raise AssertionError("disabled tenant must not call search provider")

    monkeypatch.setattr(
        "app.integrations.acquisition.search_api.fake.FakeSearchProvider.search",
        fail_search,
    )

    response = _run_advanced_search(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.feature_name == "advanced_web_search"
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0


def test_enabled_tenant_fake_advanced_search_saves_candidates(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    _enable_fake_acquisition(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    response = _run_advanced_search(client)
    html = response.get_data(as_text=True)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerCandidate, TargetCustomerDiscoveryRun

    assert response.status_code == 200
    assert "高级自动网页搜索结果已保存" in html
    assert "Atlas Global Imports" in html
    with Session(engine) as session:
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
        candidates = list(
            session.scalars(
                select(TargetCustomerCandidate).where(
                    TargetCustomerCandidate.tenant_id == tenant_id
                )
            )
        )
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))

    assert run is not None
    assert run.status == "matched"
    assert '"channel_key": "advanced_web_search"' in run.filters_json
    assert candidates
    assert candidates[0].source_channel == "advanced_web_search"
    assert candidates[0].status == "pending_review"
    assert "source_provider" in candidates[0].raw_data_json
    assert ledger is not None
    assert ledger.feature_name == "advanced_web_search"
    assert ledger.status == "success"
    assert ledger.credits_charged == 0


def test_daily_spend_cap_blocks_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    _enable_fake_acquisition(app, daily_cap=0)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_search(*_args, **_kwargs):
        raise AssertionError("daily cap block must not call search provider")

    monkeypatch.setattr(
        "app.integrations.acquisition.search_api.fake.FakeSearchProvider.search",
        fail_search,
    )

    response = _run_advanced_search(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "已达到每日花费上限" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "blocked_quota"
    assert ledger.credits_charged == 0


def test_add_to_crm_still_explicit_and_does_not_send_email(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    _enable_fake_acquisition(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _run_advanced_search(client)

    from app.modules.jobs.target_models import TargetCustomerCandidate
    from app.modules.outreach.models import OutreachMessage

    with Session(engine) as session:
        candidate = session.scalar(
            select(TargetCustomerCandidate).where(TargetCustomerCandidate.tenant_id == tenant_id)
        )
        assert candidate is not None
        candidate_id = candidate.id

    response = client.post(f"/collection/candidates/{candidate_id}/add-to-crm")

    from app.modules.leads.models import Lead

    assert response.status_code in {302, 303}
    with Session(engine) as session:
        lead = session.scalar(select(Lead).where(Lead.tenant_id == tenant_id))
        messages = session.scalar(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.tenant_id == tenant_id)
        )
    assert lead is not None
    assert messages == 0
