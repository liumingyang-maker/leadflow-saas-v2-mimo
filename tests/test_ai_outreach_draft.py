from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "ai-draft-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "ai-draft-tenant-secret-key-that-is-long-enough")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "ai-draft-outreach-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _tenant_user_lead(app, engine):
    from app.modules.accounts.models import Tenant, TenantMembership, User
    from app.modules.leads.models import Lead

    with Session(engine) as session:
        tenant = Tenant(company_name="Draft Co", status="active", plan="basic")
        user = User(
            email="owner@example.com",
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.flush()
        lead = Lead(
            tenant_id=tenant.id,
            email="buyer@example.com",
            first_name="Buyer",
            last_name="One",
            title="Owner",
            website="https://buyer.example",
            industry="Retail",
            source="manual",
            status="accepted",
        )
        session.add(lead)
        session.commit()
        tenant_id = tenant.id
        user_id = user.id
        lead_id = lead.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["tenant_id"] = tenant_id
        sess["user_id"] = user_id
        sess["tenant_email"] = "owner@example.com"
    return client, tenant_id, user_id, lead_id


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


def test_outreach_page_shows_ai_draft_controls(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, _tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)

    response = client.get(f"/leads/{lead_id}/outreach")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 草稿" in html
    assert f"/leads/{lead_id}/outreach/ai-draft" in html
    assert "生成 AI 草稿" in html


def test_fake_ai_draft_generates_text_charges_credits_and_does_not_send(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    response = client.post(
        f"/leads/{lead_id}/outreach/ai-draft",
        data={"ai_notes": "Mention fast follow-up."},
    )
    html = response.get_data(as_text=True)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.outreach.models import OutreachMessage

    assert response.status_code == 200
    assert "关于增长线索的一个想法" in html
    assert "这周是否方便简单交流一下" in html
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        message_count = session.scalar(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "success"
    assert ledger.credits_charged == 5
    assert ledger.feature_name == "outreach_draft"
    assert message_count == 0


def test_ai_draft_disabled_writes_disabled_ledger(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "该工作区尚未启用 AI" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0


def test_missing_quota_row_does_not_call_provider(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called for disabled tenant")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "请联系管理员" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "disabled"
    assert ledger.error_code == "tenant_ai_disabled"
    assert ledger.credits_charged == 0


def test_disabled_tenant_quota_does_not_call_provider(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    from app.modules.ai.models import TenantAIQuota

    with Session(engine) as session:
        quota = session.scalar(select(TenantAIQuota).where(TenantAIQuota.tenant_id == tenant_id))
        assert quota is not None
        quota.enabled = False
        session.commit()

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("provider should not be called for disabled tenant")

    monkeypatch.setattr("app.integrations.ai.fake.FakeAIProvider.generate_text", fail_generate)

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "请联系管理员" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "disabled"
    assert ledger.credits_charged == 0


def test_ai_draft_quota_block_prevents_provider_charge(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id, credits=0)

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "AI 额度不足" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "blocked_quota"
    assert ledger.credits_charged == 0


def test_english_locale_ai_draft_uses_english_fake_provider(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_fake_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    client.get("/locale/en-US?next=/login")

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Quick idea for your growth pipeline" in html
    assert "Would it make sense to compare notes this week" in html


def test_reasoning_content_draft_does_not_store_full_reasoning(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_openai_compatible_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)
    reasoning_text = "Subject: Reasoning fallback\n\nThis draft came from reasoning content."

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": reasoning_text,
                            }
                        }
                    ]
                }
            ).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})

    from app.modules.ai.models import AIUsageLedger

    assert response.status_code == 200
    assert "Reasoning fallback" in response.get_data(as_text=True)
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
    assert ledger is not None
    assert ledger.status == "success"
    assert ledger.credits_charged == 5
    assert reasoning_text not in repr(ledger.__dict__)


def test_provider_failure_keeps_manual_form_usable_and_does_not_charge(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    _enable_openai_compatible_ai(app)
    client, tenant_id, _user_id, lead_id = _tenant_user_lead(app, engine)
    _enable_tenant_ai(app, tenant_id=tenant_id)

    def fail_urlopen(*_args, **_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    response = client.post(f"/leads/{lead_id}/outreach/ai-draft", data={})
    html = response.get_data(as_text=True)

    from app.modules.ai.models import AIUsageLedger
    from app.modules.outreach.models import OutreachMessage

    assert response.status_code == 200
    assert 'action="/leads/' in html
    assert "/outreach/send" in html
    assert "无法生成 AI 草稿" in html
    with Session(engine) as session:
        ledger = session.scalar(select(AIUsageLedger).where(AIUsageLedger.tenant_id == tenant_id))
        message_count = session.scalar(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.tenant_id == tenant_id)
        )
    assert ledger is not None
    assert ledger.status == "failed"
    assert ledger.credits_charged == 0
    assert message_count == 0
