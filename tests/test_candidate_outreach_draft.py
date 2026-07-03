from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "candidate-draft-test-secret-key")
    monkeypatch.setenv("TENANT_SECRET_KEY", "candidate-draft-test-tenant-key")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "candidate-draft-test-outreach-key")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_client(app, engine, *, email: str = "owner@example.com", company: str = "Draft Co"):
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
        "selling_points_en": ["stable supply", "trial order support"],
        "target_industries": ["Retail"],
        "buyer_types": ["Importer", "Distributor"],
        "target_countries": ["United States", "Germany"],
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


def _candidate(engine, *, tenant_id: str, profile_id: str):
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
            website="https://north.example",
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


def _completed_research_report(engine, *, tenant_id: str, candidate_id: str):
    from app.modules.jobs.target_models import CandidateResearchReport

    with Session(engine) as session:
        report = CandidateResearchReport(
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            status="completed",
            provider="fake",
            search_provider="brave",
            company_name="Northstar Outdoor Supply",
            company_domain="north.example",
            country="United States",
            buyer_type="Distributor",
            fit_score=72,
            confidence_score=58,
            summary="Unverified public profile may fit outdoor retail.",
            why_potential_buyer="Possible distributor fit from supplied metadata.",
            product_fit="Drinkware may be adjacent to the product range.",
            possible_use_cases_json=json.dumps(["Catalog review"]),
            buyer_signals_json=json.dumps(
                [{"signal": "Outdoor category fit", "source": "candidate_metadata"}]
            ),
            risk_signals_json=json.dumps(
                [{"risk": "Thin source data", "source": "candidate_metadata"}]
            ),
            suggested_next_action="Manually confirm product category fit.",
            suggested_outreach_angle="Lead with trial-order support and stable supply.",
            sources_json=json.dumps(
                [
                    {
                        "title": "Northstar Outdoor Supply",
                        "url": "https://north.example",
                        "source_provider": "brave",
                        "snippet": "Public search snippet only.",
                    }
                ]
            ),
            ai_model="fake-ai",
        )
        session.add(report)
        session.commit()
        return report.id


def test_draft_route_requires_login(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    with client.session_transaction() as sess:
        sess.clear()

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_draft_route_blocks_cross_tenant_candidate(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _client_a, tenant_a, _user_a = _tenant_client(app, engine, email="a@example.com")
    client_b, _tenant_b, _user_b = _tenant_client(app, engine, email="b@example.com")
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_a)
    candidate_id = _candidate(engine, tenant_id=tenant_a, profile_id=profile_id)

    response = client_b.post(f"/collection/candidates/{candidate_id}/outreach-draft")
    view = client_b.get(f"/collection/candidates/{candidate_id}/outreach-draft")

    assert response.status_code == 404
    assert view.status_code == 404


def test_missing_candidate_returns_404(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, _tenant_id, _user_id = _tenant_client(app, engine)

    response = client.post("/collection/candidates/missing/outreach-draft")

    assert response.status_code == 404


def test_no_completed_research_report_blocks_generation(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called without completed research")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateOutreachDraft

    assert response.status_code == 200
    assert "请先生成 AI 深度背调" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger_count = session.scalar(select(func.count(AIUsageLedger.id)))
        draft_count = session.scalar(select(func.count(CandidateOutreachDraft.id)))
    assert ledger_count == 0
    assert draft_count == 0


def test_existing_completed_draft_is_reused(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    report_id = _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    from app.modules.jobs.target_models import CandidateOutreachDraft

    with Session(engine) as session:
        session.add(
            CandidateOutreachDraft(
                tenant_id=tenant_id,
                candidate_id=candidate_id,
                research_report_id=report_id,
                status="completed",
                provider="fake",
                ai_model="fake-ai",
                subject="Existing subject",
                body="Existing body",
                disclaimer="Draft only. Not sent.",
            )
        )
        session.commit()

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when draft already exists")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")
    detail = client.get(f"/collection/candidates/{candidate_id}")

    assert response.status_code in {302, 303}
    assert "Existing subject" in detail.get_data(as_text=True)
    with Session(engine) as session:
        draft_count = session.scalar(select(func.count(CandidateOutreachDraft.id)))
    assert draft_count == 1


def test_ai_disabled_writes_zero_credit_ledger_and_failed_draft(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateOutreachDraft

    assert response.status_code == 200
    assert "AI 功能暂未开启" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        draft = session.scalar(
            select(CandidateOutreachDraft).where(CandidateOutreachDraft.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.feature_name == "candidate_outreach_draft"
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0
    assert draft is not None
    assert draft.status == "failed"
    assert draft.ai_usage_ledger_id == ledger.id


def test_tenant_ai_disabled_blocks_provider_call_and_charges_zero(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when tenant AI is disabled")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "AI 功能暂未开启" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "disabled"
    assert ledger.error_code == "tenant_ai_disabled"
    assert ledger.credits_charged == 0


def test_quota_block_prevents_provider_call_and_charges_zero(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id, credits=2)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called when quota is blocked")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "额度不足" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "blocked_quota"
    assert ledger.credits_charged == 0


def test_successful_draft_writes_sanitized_row_and_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateOutreachDraft
    from app.modules.outreach.models import OutreachMessage

    assert response.status_code in {302, 303}
    detail = client.get(f"/collection/candidates/{candidate_id}")
    html = detail.get_data(as_text=True)
    assert "AI 开发信草稿" in html
    assert "Possible fit for your outdoor retail range" in html
    assert "这是草稿，不会自动发送" in html
    assert "发送前请人工确认" in html
    assert "test@example.com" not in html
    assert "415 555" not in html
    assert ">发送<" not in html
    with Session(engine) as session:
        draft = session.scalar(
            select(CandidateOutreachDraft).where(CandidateOutreachDraft.tenant_id == tenant_id)
        )
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        outreach_count = session.scalar(select(func.count(OutreachMessage.id)))
    assert draft is not None
    assert draft.status == "completed"
    assert draft.ai_usage_ledger_id == ledger.id
    assert draft.provider == "fake"
    stored = json.dumps(
        {
            "subject": draft.subject,
            "body": draft.body,
            "short_body": draft.short_body,
            "notes": draft.personalization_notes_json,
            "sources": draft.sources_json,
        },
        ensure_ascii=False,
    )
    assert "test@example.com" not in stored
    assert "415 555" not in stored
    assert "full prompt" not in draft.__table__.columns
    assert "full response" not in draft.__table__.columns
    assert "reasoning_content" not in draft.__table__.columns
    assert "raw_provider_response" not in draft.__table__.columns
    assert ledger is not None
    assert ledger.feature_name == "candidate_outreach_draft"
    assert ledger.status == "success"
    assert ledger.credits_charged == 0
    assert outreach_count == 0


def test_provider_failure_shows_safe_error_and_charges_zero(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

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

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateOutreachDraft

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        draft = session.scalar(
            select(CandidateOutreachDraft).where(CandidateOutreachDraft.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.credits_charged == 0
    assert draft is not None
    assert draft.status == "failed"


def test_malformed_json_creates_failed_draft_and_zero_credit_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    from app.integrations.ai.base import AIGenerationResult

    def malformed_generate(*_args, **_kwargs):
        return AIGenerationResult(success=True, text="{}", provider="fake", model="fake-ai")

    monkeypatch.setattr(
        "app.integrations.ai.fake.FakeAIProvider.generate_text",
        malformed_generate,
    )

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.ai.models import AIUsageLedger
    from app.modules.jobs.target_models import CandidateOutreachDraft

    assert response.status_code == 200
    assert "系统繁忙，请稍后重试" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        draft = session.scalar(
            select(CandidateOutreachDraft).where(CandidateOutreachDraft.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.error_code == "malformed_json"
    assert ledger.credits_charged == 0
    assert draft is not None
    assert draft.status == "failed"
    assert draft.error_code == "malformed_json"


def test_provider_private_contact_output_is_stripped_before_storage(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id = _tenant_client(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    profile_id = _confirmed_product_profile(engine, tenant_id=tenant_id)
    candidate_id = _candidate(engine, tenant_id=tenant_id, profile_id=profile_id)
    _completed_research_report(engine, tenant_id=tenant_id, candidate_id=candidate_id)

    from app.integrations.ai.base import AIGenerationResult

    def unsafe_generate(*_args, **_kwargs):
        text = json.dumps(
            {
                "subject": "Email john@example.com",
                "body": "Call +1 415 555 1212. This is not safe.",
                "short_body": "Reach john@example.com",
                "follow_up_angle": "Call +1 415 555 1212",
                "personalization_notes": ["Contact john@example.com"],
                "confidence_note": "No verified buyer claim.",
                "disclaimer": "Draft only. Not sent.",
            }
        )
        return AIGenerationResult(success=True, text=text, provider="fake", model="fake-ai")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", unsafe_generate)

    response = client.post(f"/collection/candidates/{candidate_id}/outreach-draft")

    from app.modules.jobs.target_models import CandidateOutreachDraft

    assert response.status_code in {302, 303}
    with Session(engine) as session:
        draft = session.scalar(
            select(CandidateOutreachDraft).where(CandidateOutreachDraft.tenant_id == tenant_id)
        )
    assert draft is not None
    stored = json.dumps(
        {
            "subject": draft.subject,
            "body": draft.body,
            "short_body": draft.short_body,
            "follow_up_angle": draft.follow_up_angle,
            "notes": draft.personalization_notes_json,
        },
        ensure_ascii=False,
    )
    assert "john@example.com" not in stored
    assert "415 555" not in stored
