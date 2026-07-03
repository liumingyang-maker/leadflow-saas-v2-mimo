from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "acquisition-test-secret-key-that-is-long-enough")
    monkeypatch.setenv(
        "TENANT_SECRET_KEY", "acquisition-test-tenant-secret-key-that-is-long-enough"
    )
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "acquisition-test-outreach-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Acq Co"):
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


def _generate_strategy(client):
    return client.post(
        "/collection/channels/basic-search/strategy",
        data={"country": "", "buyer_type": "", "industry": "", "result_count": "10"},
    )


def test_collection_requires_login(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)

    response = app.test_client().get("/collection")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_channel_hub_displays_available_and_future_channels(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    response = client.get("/collection")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "获客渠道" in html
    assert "AI 普通搜索" in html
    assert "CSV 导入" in html
    assert "手动添加" in html
    assert "自动网页搜索" in html
    assert "地图商家" in html
    assert "B2B 目录" in html
    assert "海关数据" in html
    assert "该渠道暂未开放" in html
    assert "/collection/channels/auto_web_search_api" not in html


def test_no_product_profile_shows_train_prompt(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, _tenant_id, _user_id = _tenant_client(app, engine)

    response = client.get("/collection")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "请先训练你的 AI 外贸员" in html
    assert "/onboarding/product-profile" in html


def test_disabled_tenant_cannot_generate_basic_search_strategy(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called for disabled tenant")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = _generate_strategy(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.feature_name == "basic_search_strategy_generation"
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0


def test_enabled_tenant_generates_strategy_links_without_fetching(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("basic search must not fetch generated search links")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    response = _generate_strategy(client)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerDiscoveryRun

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "搜索策略已生成" in html
    assert "https://www.google.com/search" in html
    assert "https://www.bing.com/search" in html
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
    assert ledger is not None
    assert ledger.feature_name == "basic_search_strategy_generation"
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert run is not None
    assert run.status == "planned"
    assert "search_links" in run.generated_plan_json


def test_pasted_search_results_parse_to_sanitized_candidates(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _generate_strategy(client)

    response = client.post(
        "/collection/channels/basic-search/parse-results",
        data={
            "result_count": "10",
            "pasted_results": (
                "Atlas Promo Supply https://atlas-promo.example buyer@example.com "
                "+1 555 123 4567 distributor"
            ),
        },
    )

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerCandidate

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "搜索结果已整理为候选客户" in html
    assert "Atlas Promo Supply" in html
    assert "buyer@example.com" not in html
    assert "+1 555" not in html
    with Session(engine) as session:
        candidates = list(
            session.scalars(
                select(TargetCustomerCandidate).where(
                    TargetCustomerCandidate.tenant_id == tenant_id
                )
            )
        )
        ledgers = list(
            session.scalars(
                select(AIUsageLedger)
                .where(AIUsageLedger.tenant_id == tenant_id)
                .order_by(AIUsageLedger.created_at)
            )
        )
    assert candidates
    assert candidates[0].source_channel == "pasted_search_results"
    assert candidates[0].status == "pending_review"
    assert "buyer@example.com" not in candidates[0].raw_data_json
    assert ledgers[-1].feature_name == "pasted_search_result_parsing"
    assert ledgers[-1].status == "success"
    assert ledgers[-1].credits_charged == 0


def test_add_to_crm_remains_explicit_and_does_not_send_email(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _generate_strategy(client)
    client.post(
        "/collection/channels/basic-search/parse-results",
        data={"result_count": "10", "pasted_results": "Atlas Promo Supply atlas-promo.example"},
    )

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


def test_no_new_external_api_dependency_in_acquisition_modules() -> None:
    from pathlib import Path

    root = Path("app/integrations/acquisition")
    text = "\n".join(path.read_text() for path in root.glob("*.py"))

    assert "requests." not in text
    assert "httpx" not in text
    assert "urlopen" not in text
    assert "BeautifulSoup" not in text
    assert "selenium" not in text
    assert "playwright" not in text
