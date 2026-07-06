from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "manual-paste-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "manual-paste-test-tenant-key-that-is-long-enough")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "manual-paste-test-outreach-key-that-is-long")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Paste Co"):
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
        "product_keywords_en": [
            "eco-friendly packaging",
            "compostable mailer bags",
            "custom packaging bags",
        ],
        "target_industries": ["Packaging", "Food packaging", "Cosmetics"],
        "buyer_types": ["Importer", "Distributor", "Private label brand"],
        "target_countries": ["United States", "Germany", "United Kingdom"],
        "search_keywords": ["eco-friendly packaging importer", "custom packaging bags"],
        "negative_keywords": ["manufacturer", "factory", "supplier"],
    }
    with Session(engine) as session:
        profile = TenantProductProfile(
            tenant_id=tenant_id,
            raw_company_intro="Packaging export factory",
            raw_products="Eco-friendly packaging bags and compostable mailer bags",
            extracted_profile_json=json.dumps(profile_json),
            status="confirmed",
            confirmed_at=datetime.now(UTC),
        )
        session.add(profile)
        session.commit()
        return profile.id


def _parse(client, *, pasted_text: str = "GreenPack Distribution\nhttps://greenpack.example"):
    return client.post(
        "/collection/search-intent/parse",
        data={
            "source_type": "search_engine_results",
            "pasted_text": pasted_text,
            "user_note": "Germany distributors",
            "country": "Germany",
            "buyer_type": "Distributor",
            "industry": "Packaging",
            "result_count": "10",
        },
    )


def test_paste_parser_route_requires_login(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = app.test_client()

    response = client.post("/collection/search-intent/parse")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_search_intent_page_displays_paste_parser_ui(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    client.post("/collection/search-intent", data={"result_count": "10"})

    response = client.get("/collection/search-intent")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "粘贴搜索结果" in html
    assert "AI 解析并生成候选客户" in html
    assert "不会自动访问或抓取网页" in html
    assert "不会自动发送邮件" in html
    assert "不会保存私人邮箱/手机号" in html
    assert "候选客户未验证" in html


def test_no_product_profile_blocks_without_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called without product profile")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = _parse(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "请先训练你的 AI 外贸员" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger_count = session.scalar(select(func.count(AIUsageLedger.id)))
    assert ledger_count == 0


def test_empty_pasted_text_blocks_without_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called without pasted text")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = _parse(client, pasted_text="")

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "粘贴搜索结果" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger_count = session.scalar(select(func.count(AIUsageLedger.id)))
    assert ledger_count == 0


def test_global_ai_disabled_blocks_provider_call(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    response = _parse(client)

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.feature_name == "search_result_paste_parser_v2"
    assert ledger.status == "disabled"
    assert ledger.error_code == "ai_disabled"
    assert ledger.credits_charged == 0


def test_tenant_ai_disabled_and_quota_blocked_do_not_call_provider(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when tenant AI is blocked")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    disabled_response = _parse(client)
    _enable_tenant_ai(app, tenant_id=tenant_id, credits=0)
    quota_response = _parse(client)

    from app.modules.ai.models import AIUsageLedger

    assert disabled_response.status_code == 200
    assert quota_response.status_code == 200
    assert "该工作区尚未启用 AI" in disabled_response.get_data(as_text=True)
    assert "额度不足" in quota_response.get_data(as_text=True)
    with Session(engine) as session:
        ledgers = list(
            session.scalars(
                select(AIUsageLedger)
                .where(AIUsageLedger.tenant_id == tenant_id)
                .order_by(AIUsageLedger.created_at)
            )
        )
    assert [ledger.status for ledger in ledgers] == ["disabled", "blocked_quota"]
    assert all(ledger.credits_charged == 0 for ledger in ledgers)


def test_success_saves_buyer_and_maybe_buyer_candidates_only(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    response = _parse(
        client,
        pasted_text=(
            "Google snippet: GreenPack Distribution sustainable packaging distributor\n"
            "CSV: Eco Retail Brands, Germany, private label brand\n"
            "Directory result: example directory supplier list\n"
        ),
    )

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerCandidate, TargetCustomerDiscoveryRun
    from app.modules.outreach.models import OutreachMessage

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "搜索结果已整理为候选客户" in html
    assert "粘贴解析结果" in html
    assert "已保存候选客户" in html
    assert "已拒绝项目" in html
    assert "GreenPack Distribution" in html
    assert "North Market Import" in html
    assert "Add to CRM" not in html
    assert "加入 CRM" in html
    assert "verified buyer" not in html.lower()
    assert "purchase intent" not in html.lower()
    assert "@" not in html
    with Session(engine) as session:
        candidates = list(
            session.scalars(
                select(TargetCustomerCandidate)
                .where(TargetCustomerCandidate.tenant_id == tenant_id)
                .order_by(TargetCustomerCandidate.created_at)
            )
        )
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        outreach_count = session.scalar(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.tenant_id == tenant_id)
        )
    assert len(candidates) == 3
    assert all(candidate.status == "pending_review" for candidate in candidates)
    assert all(
        candidate.source_channel == "manual_search_paste_parser_v2" for candidate in candidates
    )
    assert run is not None
    assert run.status == "matched"
    assert run.generated_count == 3
    plan = json.loads(run.generated_plan_json)
    assert plan["parse_summary"]["saved_candidate_count"] == 3
    assert plan["parse_summary"]["rejected_count"] == 3
    assert "pasted text" not in run.generated_plan_json.lower()
    assert "full_prompt" not in run.generated_plan_json
    assert "full_response" not in run.generated_plan_json
    assert "reasoning_content" not in run.generated_plan_json
    assert "raw provider" not in run.generated_plan_json.lower()
    assert ledger is not None
    assert ledger.feature_name == "search_result_paste_parser_v2"
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert outreach_count == 0


def test_duplicate_domain_and_company_country_are_skipped(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    from app.modules.jobs.target_models import TargetCustomerCandidate, TargetCustomerDiscoveryRun

    with Session(engine) as session:
        existing_run = TargetCustomerDiscoveryRun(
            tenant_id=tenant_id,
            product_profile_id=profile_id,
            filters_json=json.dumps({"channel_key": "existing"}),
            generated_plan_json="{}",
            status="matched",
        )
        session.add(existing_run)
        session.flush()
        session.add(
            TargetCustomerCandidate(
                tenant_id=tenant_id,
                run_id=existing_run.id,
                company_name="GreenPack Distribution",
                website="https://greenpack-distribution.example",
                country="United States",
                source_channel="existing",
                status="pending_review",
            )
        )
        session.commit()

    response = _parse(client)

    with Session(engine) as session:
        candidates = list(
            session.scalars(
                select(TargetCustomerCandidate).where(
                    TargetCustomerCandidate.tenant_id == tenant_id
                )
            )
        )
        latest_run = session.scalar(
            select(TargetCustomerDiscoveryRun)
            .where(TargetCustomerDiscoveryRun.tenant_id == tenant_id)
            .order_by(TargetCustomerDiscoveryRun.created_at.desc())
        )
    assert response.status_code == 200
    assert len(candidates) == 3
    assert latest_run is not None
    plan = json.loads(latest_run.generated_plan_json)
    assert plan["parse_summary"]["duplicate_count"] == 1
    assert latest_run.generated_count == 2


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

    response = _parse(client)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import TargetCustomerDiscoveryRun

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.credits_charged == 0
    assert run is not None
    assert run.status == "failed"
    assert run.generated_count == 0


def test_safety_sanitizes_private_contact_social_scrape_and_verified_claims(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _confirmed_product_profile(engine, tenant_id=tenant_id)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    from app.integrations.ai.base import AIGenerationResult

    def unsafe_provider(self, request):
        text = json.dumps(
            {
                "parse_summary": {
                    "source_type": "manual_company_list",
                    "total_items_seen": 3,
                    "candidate_count": 2,
                    "rejected_count": 1,
                    "duplicate_hint_count": 0,
                    "safety_warnings": ["contains buyer@example.com and +1 555 123 4567"],
                },
                "candidates": [
                    {
                        "source_item_id": "item_001",
                        "company_name": "Safe Buyer buyer@example.com",
                        "domain": "safebuyer.example",
                        "source_url": "https://safebuyer.example/contact",
                        "country": "Germany",
                        "buyer_type": "verified buyer",
                        "classification": "buyer",
                        "product_fit": "high",
                        "source_quality": "official_site",
                        "fit_score": 88,
                        "confidence_score": 72,
                        "match_reason": "purchase intent from LinkedIn profile",
                        "risk_reason": "crawl Facebook and send email",
                        "next_action": "automatic email campaign",
                        "sanitized_snippet": "WhatsApp +1 555 123 4567 Telegram handle",
                    }
                ],
                "rejected_items": [{"source_item_id": "item_002", "reason": "scrape linkedin"}],
                "query_feedback": {
                    "suggested_negative_keywords": ["supplier"],
                    "suggested_better_queries": ["packaging importer -supplier"],
                    "domain_blacklist_suggestions": ["directory.example"],
                    "notes": ["do not crawl"],
                },
            }
        )
        return AIGenerationResult(success=True, text=text, provider="fake", model="fake-ai")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", unsafe_provider)

    response = _parse(
        client,
        pasted_text=(
            "Safe Buyer buyer@example.com +1 555 123 4567\n"
            "https://linkedin.com/in/private-contact\nWhatsApp: hidden\n"
        ),
    )

    from app.modules.jobs.target_models import TargetCustomerCandidate, TargetCustomerDiscoveryRun

    assert response.status_code == 200
    with Session(engine) as session:
        candidate = session.scalar(
            select(TargetCustomerCandidate).where(TargetCustomerCandidate.tenant_id == tenant_id)
        )
        run = session.scalar(
            select(TargetCustomerDiscoveryRun).where(
                TargetCustomerDiscoveryRun.tenant_id == tenant_id
            )
        )
    assert candidate is not None
    assert run is not None
    saved = (
        f"{candidate.company_name} {candidate.match_reason} "
        f"{candidate.raw_data_json} {run.generated_plan_json}"
    ).lower()
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


def test_cross_tenant_candidates_are_not_visible(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client_a, tenant_a, _user_a = _tenant_client(app, engine, email="a@example.com")
    client_b, tenant_b, _user_b = _tenant_client(app, engine, email="b@example.com")
    _confirmed_product_profile(engine, tenant_id=tenant_a)
    _confirmed_product_profile(engine, tenant_id=tenant_b)
    _enable_tenant_ai(app, tenant_id=tenant_a)
    _enable_tenant_ai(app, tenant_id=tenant_b)

    _parse(client_a)
    response_b = client_b.get("/collection/search-intent")

    html_b = response_b.get_data(as_text=True)
    assert response_b.status_code == 200
    assert "GreenPack Distribution" not in html_b
