from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "target-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "target-test-tenant-secret-key-that-is-long-enough")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "target-test-outreach-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Target Co"):
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


def _generate_plan_and_candidates(client):
    plan = client.post(
        "/collection/target-plan",
        data={"country": "", "buyer_type": "", "industry": "", "result_count": "10"},
    )
    match = client.post("/collection/target-match", data={"result_count": "10"})
    return plan, match


def test_collection_requires_login(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)

    response = app.test_client().get("/collection")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_no_confirmed_product_profile_shows_train_prompt(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, _tenant_id, _user_id = _tenant_client(app, engine)

    response = client.get("/collection")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "请先训练你的 AI 外贸员" in html
    assert "/onboarding/product-profile" in html


def test_disabled_tenant_cannot_generate_target_plan_and_writes_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called for disabled tenant")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post("/collection/target-plan", data={"result_count": "10"})

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.feature_name == "target_customer_plan_generation"
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0


def test_enabled_tenant_generates_fake_plan_with_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    response = client.post("/collection/target-plan", data={"result_count": "10"})

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerDiscoveryRun

    assert response.status_code == 200
    assert "insulated bottle importer" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
    assert ledger is not None
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert run is not None
    assert run.status == "planned"
    assert "ideal_buyer_types" in run.generated_plan_json


def test_candidate_matching_generates_cards_and_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    _plan, match = _generate_plan_and_candidates(client)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerCandidate

    html = match.get_data(as_text=True)
    assert match.status_code == 200
    assert "Northstar Outdoor Supply" in html
    assert "加入 CRM" in html
    assert "verified buyer" not in html.lower()
    assert "@" not in html
    with Session(engine) as session:
        candidate_count = session.scalar(
            select(func.count(TargetCustomerCandidate.id)).where(
                TargetCustomerCandidate.tenant_id == tenant_id
            )
        )
        ledgers = list(
            session.scalars(
                select(AIUsageLedger)
                .where(AIUsageLedger.tenant_id == tenant_id)
                .order_by(AIUsageLedger.created_at)
            )
        )
    assert candidate_count == 3
    assert ledgers[-1].feature_name == "target_customer_candidate_matching"
    assert ledgers[-1].status == "success"
    assert ledgers[-1].credits_charged == 0


def test_provider_failure_and_malformed_json_are_safe(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_openai_compatible_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_urlopen(*_args, **_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    failed = client.post("/collection/target-plan", data={"result_count": "10"})

    assert failed.status_code == 200
    assert "系统繁忙，请稍后重试" in failed.get_data(as_text=True)

    _enable_fake_ai(app)
    from app.integrations.ai.base import AIGenerationResult

    def malformed(self, request):
        return AIGenerationResult(success=True, text="{bad json", provider="fake", model="fake")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", malformed)
    malformed_response = client.post("/collection/target-plan", data={"result_count": "10"})

    assert malformed_response.status_code == 200
    assert "系统繁忙，请稍后重试" in malformed_response.get_data(as_text=True)


def test_add_candidate_to_crm_is_explicit_and_does_not_send_email(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _generate_plan_and_candidates(client)

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
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        lead = session.scalar(select(Lead).where(Lead.tenant_id == tenant_id))
        messages = session.scalar(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.tenant_id == tenant_id)
        )
    assert candidate is not None
    assert candidate.status == "added_to_crm"
    assert lead is not None
    assert lead.status == "pending_review"
    assert lead.source == "collection"
    assert messages == 0


def test_duplicate_candidate_is_marked_duplicate(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _generate_plan_and_candidates(client)

    from app.modules.jobs.target_models import TargetCustomerCandidate
    from app.modules.leads.models import Company, Lead

    with Session(engine) as session:
        candidate = session.scalar(
            select(TargetCustomerCandidate).where(TargetCustomerCandidate.tenant_id == tenant_id)
        )
        assert candidate is not None
        company = Company(
            tenant_id=tenant_id,
            name=candidate.company_name,
            domain="northstar-outdoor.example",
        )
        session.add(Lead(tenant_id=tenant_id, company=company, source="collection"))
        session.commit()
        candidate_id = candidate.id

    response = client.post(f"/collection/candidates/{candidate_id}/add-to-crm")

    assert response.status_code == 200
    assert "检测到重复候选客户" in response.get_data(as_text=True)
    with Session(engine) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
    assert candidate is not None
    assert candidate.status == "duplicate"


def test_candidates_are_tenant_isolated(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client_a, tenant_a, _user_a = _tenant_client(app, engine, email="a@example.com", company="A")
    client_b, tenant_b, _user_b = _tenant_client(app, engine, email="b@example.com", company="B")
    _enable_tenant_ai(app, tenant_id=tenant_a)
    _enable_tenant_ai(app, tenant_id=tenant_b)
    _confirmed_product_profile(engine, tenant_id=tenant_a)
    _confirmed_product_profile(engine, tenant_id=tenant_b)

    _generate_plan_and_candidates(client_a)
    response_b = client_b.get("/collection")

    assert tenant_a != tenant_b
    assert "Northstar Outdoor Supply" not in response_b.get_data(as_text=True)


def test_private_contact_fields_from_provider_are_not_stored_or_shown(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    client.post("/collection/target-plan", data={"result_count": "10"})

    from app.integrations.ai.base import AIGenerationResult

    def candidate_with_private_contact(self, request):
        return AIGenerationResult(
            success=True,
            text=json.dumps(
                {
                    "candidates": [
                        {
                            "company_name": "Safe Candidate",
                            "country": "US",
                            "website": "https://safe.example",
                            "industry": "Retail",
                            "buyer_type": "Importer",
                            "source_channel": "示例客户",
                            "match_reason": "Contact buyer@example.com or +1 555 123 4567",
                            "confidence_score": 70,
                            "suggested_next_action": "Review before using",
                            "email": "buyer@example.com",
                            "phone": "+1 555 123 4567",
                        }
                    ]
                }
            ),
            provider="fake",
            model="fake",
        )

    monkeypatch.setattr(
        "app.integrations.ai.fake.FakeAIProvider.generate_text",
        candidate_with_private_contact,
    )

    response = client.post("/collection/target-match", data={"result_count": "10"})
    html = response.get_data(as_text=True)

    from app.modules.jobs.target_models import TargetCustomerCandidate

    assert response.status_code == 200
    assert "buyer@example.com" not in html
    assert "+1 555" not in html
    with Session(engine) as session:
        candidate = session.scalar(
            select(TargetCustomerCandidate).where(TargetCustomerCandidate.tenant_id == tenant_id)
        )
    assert candidate is not None
    assert "buyer@example.com" not in candidate.raw_data_json
    assert "buyer@example.com" not in candidate.match_reason
