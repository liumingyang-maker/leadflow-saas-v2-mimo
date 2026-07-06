from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "search-intent-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "search-intent-test-tenant-key-that-is-long-enough")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "search-intent-test-outreach-key-that-is-long")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Intent Co"):
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
        max_output_tokens=1200,
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
        "product_keywords_en": ["eco-friendly packaging", "LED lighting"],
        "target_industries": ["Packaging", "Lighting retail"],
        "buyer_types": ["Importer", "Distributor"],
        "target_countries": ["United States", "Germany", "Spain"],
        "search_keywords": ["eco-friendly packaging importer", "LED lighting distributor"],
        "negative_keywords": ["manufacturer", "factory", "supplier"],
    }
    with Session(engine) as session:
        profile = TenantProductProfile(
            tenant_id=tenant_id,
            raw_company_intro="Packaging and LED export factory",
            raw_products="Eco-friendly packaging bags and decorative LED lighting",
            extracted_profile_json=json.dumps(profile_json),
            status="confirmed",
            confirmed_at=datetime.now(UTC),
        )
        session.add(profile)
        session.commit()
        return profile.id


def _generate(client):
    return client.post(
        "/collection/search-intent",
        data={"country": "Germany", "buyer_type": "", "industry": "", "result_count": "10"},
    )


def test_search_intent_routes_require_login(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = app.test_client()

    get_response = client.get("/collection/search-intent")
    post_response = client.post("/collection/search-intent")

    assert get_response.status_code in {302, 303}
    assert get_response.headers["Location"].endswith("/login")
    assert post_response.status_code in {302, 303}
    assert post_response.headers["Location"].endswith("/login")


def test_no_product_profile_blocks_generation_without_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called without product profile")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = _generate(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "请先训练你的 AI 外贸员" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger_count = session.scalar(select(func.count(AIUsageLedger.id)))
    assert ledger_count == 0


def test_global_ai_disabled_blocks_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    response = _generate(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.feature_name == "search_intent_query_matrix"
    assert ledger.status == "disabled"
    assert ledger.error_code == "ai_disabled"
    assert ledger.credits_charged == 0


def test_tenant_ai_disabled_blocks_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called for disabled tenant")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = _generate(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "disabled"
    assert ledger.error_code == "tenant_ai_disabled"
    assert ledger.credits_charged == 0


def test_quota_blocked_blocks_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id, credits=0)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when quota is blocked")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = _generate(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "额度不足" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "blocked_quota"
    assert ledger.error_code == "insufficient_credits"
    assert ledger.credits_charged == 0


def test_success_generates_and_displays_query_matrix(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    response = _generate(client)
    html = response.get_data(as_text=True)
    existing = client.get("/collection/search-intent").get_data(as_text=True)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerDiscoveryRun
    from app.modules.outreach.models import OutreachMessage

    assert response.status_code == 200
    assert "AI 搜索策略" in html
    assert "搜索词矩阵" in html
    assert "复制搜索词" in html
    assert "不会自动爬网页" in html
    assert "不会自动发送邮件" in html
    assert "不是已验证客户" in html
    assert "Importer" in html
    assert "Distributor" in html
    assert "manufacturer" in html
    assert "eco-friendly packaging importer" in html
    assert "搜索词矩阵" in existing
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
        outreach_count = session.scalar(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.feature_name == "search_intent_query_matrix"
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert run is not None
    assert run.status == "planned"
    assert run.generated_count == 0
    data = json.loads(run.generated_plan_json)
    assert len(data["query_matrix"]) <= 30
    assert len(data["multilingual_terms"]) <= 5
    assert data["query_self_check"]
    assert data["next_search_steps"]
    assert "test@example.com" not in run.generated_plan_json
    assert "+1 555" not in run.generated_plan_json
    assert "full_prompt" not in run.generated_plan_json
    assert "full_response" not in run.generated_plan_json
    assert "reasoning_content" not in run.generated_plan_json
    assert "raw provider" not in run.generated_plan_json.lower()
    assert outreach_count == 0


def test_provider_failure_shows_safe_error_and_charges_zero(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    from app.integrations.ai.base import AIGenerationResult

    def fail_provider(self, request):
        return AIGenerationResult(success=False, error_code="provider_error", provider="fake")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_provider)

    response = _generate(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.credits_charged == 0


def test_output_safety_strips_private_contact_and_unsafe_instructions(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    from app.integrations.ai.base import AIGenerationResult

    def unsafe_provider(self, request):
        text = json.dumps(
            {
                "intent_summary": "Find packaging buyers. Email buyer@example.com +1 555 123 4567",
                "product_keywords": ["packaging buyer@example.com"],
                "product_synonyms": ["custom packaging"],
                "use_cases": ["crawl LinkedIn profiles", "coffee roasters"],
                "target_industries": ["Retail"],
                "buyer_roles": ["procurement"],
                "buyer_company_types": ["Importer", "verified buyer"],
                "target_countries": ["Germany"],
                "negative_keywords": ["supplier", "factory"],
                "supplier_exclusion_terms": ["manufacturer"],
                "marketplace_exclusion_terms": ["Amazon"],
                "directory_noise_terms": ["directory"],
                "multilingual_terms": [
                    {
                        "country": "Germany",
                        "language": "German",
                        "buyer_terms": ["Importeur", "phone enrichment"],
                        "query_terms": ["custom packaging Importeur buyer@example.com"],
                        "negative_terms": ["Hersteller"],
                    }
                ],
                "query_matrix": [
                    {
                        "group": "buyer_type",
                        "query": "custom packaging importer buyer@example.com -supplier",
                        "target_country": "Germany",
                        "buyer_type": "Importer",
                        "why_useful": "Do not scrape LinkedIn",
                        "risk": "not verified",
                        "copy_label": "Germany importer",
                    }
                ],
                "query_self_check": [
                    {
                        "query": "custom packaging",
                        "risk": "too broad",
                        "improved_query": "custom packaging importer +1 555 123 4567 -supplier",
                    }
                ],
                "next_search_steps": ["manually search and paste results", "send email campaign"],
            }
        )
        return AIGenerationResult(success=True, text=text, provider="fake", model="fake-ai")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", unsafe_provider)

    response = _generate(client)

    from app.modules.jobs.target_models import TargetCustomerDiscoveryRun

    assert response.status_code == 200
    with Session(engine) as session:
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
    assert run is not None
    saved = run.generated_plan_json.lower()
    assert "buyer@example.com" not in saved
    assert "+1 555" not in saved
    assert "linkedin" not in saved
    assert "facebook" not in saved
    assert "whatsapp" not in saved
    assert "telegram" not in saved
    assert "scrape" not in saved
    assert "crawl" not in saved
    assert "send email" not in saved
    assert "verified buyer" not in saved
    assert "purchase intent" not in saved
