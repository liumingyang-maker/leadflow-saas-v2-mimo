from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "profile-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "profile-test-tenant-secret-key-that-is-long-enough")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "profile-test-outreach-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Export Co"):
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


def _enable_openai_compatible_ai(app) -> None:
    from app.modules.ai.service import save_provider_settings

    save_provider_settings(
        app,
        provider="openai_compatible",
        enabled=True,
        base_url="https://api.example.test/v1",
        model="mimo-test",
        api_key="test-key",
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


def _profile_form(**overrides: str) -> dict[str, str]:
    data = {
        "raw_company_intro": "We are a small factory exporting stainless steel bottles.",
        "raw_products": "Insulated bottles, sports bottles, gift bottles",
        "raw_website_url": "https://factory.example",
        "raw_target_markets": "United States, Germany",
        "raw_advantages": "Stable delivery and small trial orders",
        "raw_certificates": "LFGB",
        "raw_moq": "500 pieces",
        "raw_delivery_capacity": "30000 pieces per month",
        "raw_customer_countries": "Germany",
    }
    data.update(overrides)
    return data


def test_onboarding_product_profile_requires_login(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)

    response = app.test_client().get("/onboarding/product-profile")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_workbench_shows_non_blocking_product_profile_entry(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, _tenant_id, _user_id = _tenant_client(app, engine)

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "训练你的 AI 外贸员" in html
    assert "/onboarding/product-profile" in html
    assert "稍后再说" in html


def test_disabled_tenant_cannot_extract_and_writes_disabled_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called for disabled tenant")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post("/onboarding/product-profile/extract", data=_profile_form())

    from app.modules.ai.models import AIUsageLedger
    from app.modules.onboarding.models import TenantProductProfile

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        profile = session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.feature_name == "product_profile_extraction"
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0
    assert profile is not None
    assert profile.raw_products.startswith("Insulated bottles")


def test_enabled_tenant_extracts_fake_profile_with_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    response = client.post("/onboarding/product-profile/extract", data=_profile_form())
    html = response.get_data(as_text=True)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.onboarding.models import TenantProductProfile
    from app.modules.onboarding.service import parse_profile_json

    assert response.status_code == 200
    assert "sample product" in html
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        profile = session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert profile is not None
    assert profile.status == "extracted"
    assert profile.last_extracted_at is not None
    parsed = parse_profile_json(profile.extracted_profile_json)
    assert parsed["product_keywords_en"] == ["sample product", "export product"]


def test_user_can_edit_and_confirm_profile(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    client.post("/onboarding/product-profile/extract", data=_profile_form())

    response = client.post(
        "/onboarding/product-profile/confirm",
        data={
            **_profile_form(),
            "product_keywords_cn": "保温杯\n运动水杯",
            "product_keywords_en": "insulated bottle\nsports bottle",
            "product_categories": "Drinkware",
            "selling_points_cn": "小单快交",
            "selling_points_en": "Fast small-batch delivery",
            "target_industries": "Retail",
            "buyer_types": "Importer",
            "target_countries": "United States",
            "search_keywords": "bottle importer",
            "negative_keywords": "jobs",
            "outreach_angles": "trial order",
            "certificates": "LFGB",
            "suggested_email_tone": "concise",
            "product_summary_en": "Insulated bottle factory.",
            "moq_summary": "500 pieces",
            "delivery_capacity": "30000 per month",
            "factory_type": "factory",
            "ideal_buyer_profile": "Importers buying drinkware.",
            "oem_odm_capability": "OEM supported",
            "price_positioning": "mid-market",
        },
    )

    from app.modules.onboarding.models import TenantProductProfile
    from app.modules.onboarding.service import parse_profile_json

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/workbench")
    with Session(engine) as session:
        profile = session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )
    assert profile is not None
    assert profile.status == "confirmed"
    assert profile.confirmed_at is not None
    assert profile.version >= 3
    parsed = parse_profile_json(profile.extracted_profile_json)
    assert parsed["product_keywords_en"] == ["insulated bottle", "sports bottle"]
    assert parsed["oem_odm_capability"] == "OEM supported"


def test_product_profile_is_tenant_isolated(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client_a, tenant_a, _user_a = _tenant_client(app, engine, email="a@example.com", company="A")
    client_b, tenant_b, _user_b = _tenant_client(app, engine, email="b@example.com", company="B")
    _enable_tenant_ai(app, tenant_id=tenant_a)
    client_a.post(
        "/onboarding/product-profile/confirm",
        data={
            **_profile_form(raw_products="Tenant A private product"),
            "product_keywords_en": "private product",
        },
    )

    response = client_b.get("/settings/product-profile")

    assert tenant_a != tenant_b
    assert response.status_code == 200
    assert "Tenant A private product" not in response.get_data(as_text=True)


def test_website_url_is_saved_but_not_fetched(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    def fail_fetch(*_args, **_kwargs):
        raise AssertionError("alpha.4 must not fetch website URLs")

    monkeypatch.setattr("urllib.request.urlopen", fail_fetch)

    response = client.post(
        "/onboarding/product-profile/extract",
        data=_profile_form(raw_website_url="factory.example/catalog"),
    )

    from app.modules.onboarding.models import TenantProductProfile

    assert response.status_code == 200
    assert "官网 URL 已按文本保存" in response.get_data(as_text=True)
    with Session(engine) as session:
        profile = session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )
    assert profile is not None
    assert profile.raw_website_url == "factory.example/catalog"


def test_provider_failure_shows_busy_and_does_not_charge(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_openai_compatible_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    def fail_urlopen(*_args, **_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    response = client.post("/onboarding/product-profile/extract", data=_profile_form())

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.credits_charged == 0


def test_malformed_json_is_failed_and_raw_response_is_not_stored(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    from app.integrations.ai.base import AIGenerationResult

    def malformed(self, request):
        return AIGenerationResult(
            success=True,
            text='{"product_keywords_en": ["do-not-store-this"',
            provider="fake",
            model="fake-ai",
        )

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", malformed)

    response = client.post("/onboarding/product-profile/extract", data=_profile_form())

    from app.modules.ai.models import AIUsageLedger
    from app.modules.onboarding.models import TenantProductProfile

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        profile = session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.error_code == "malformed_json"
    assert profile is not None
    assert "do-not-store-this" not in profile.extracted_profile_json


def test_settings_product_profile_requires_login_and_can_update(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)

    anonymous = app.test_client().get("/settings/product-profile")
    assert anonymous.status_code in {302, 303}
    assert anonymous.headers["Location"].endswith("/login")

    response = client.post(
        "/settings/product-profile/update",
        data={**_profile_form(), "product_keywords_en": "saved keyword", "action": "confirm"},
    )

    from app.modules.onboarding.models import TenantProductProfile
    from app.modules.onboarding.service import parse_profile_json

    assert response.status_code == 200
    assert "产品资料已保存" in response.get_data(as_text=True)
    with Session(engine) as session:
        profile = session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )
        count = session.scalar(
            select(func.count(TenantProductProfile.id)).where(
                TenantProductProfile.tenant_id == tenant_id
            )
        )
    assert profile is not None
    assert count == 1
    assert parse_profile_json(profile.extracted_profile_json)["product_keywords_en"] == [
        "saved keyword"
    ]
