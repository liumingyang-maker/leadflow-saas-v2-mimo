"""Core SaaS journey acceptance coverage without a browser runtime."""

from __future__ import annotations

import re
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "core-journey-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "core-journey-tenant-secret-key")
    monkeypatch.delenv("SMTP_HOST", raising=False)

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _safe_text(response) -> str:
    text = response.get_data(as_text=True)
    assert "Traceback" not in text
    assert "OperationalError" not in text
    assert "sqlalchemy.exc" not in text
    return text


def test_core_saas_user_journey_via_flask_client(monkeypatch) -> None:
    flask_app, engine = _app(monkeypatch)
    client = flask_app.test_client()

    from app.modules.accounts.models import EmailToken, Tenant
    from app.modules.leads.models import Activity, Lead
    from app.modules.outreach.models import OutreachMessage

    register = client.post(
        "/register",
        data={
            "email": "trial-owner@example.com",
            "password": "safe-password-123",
            "company_name": "Trial Operator Co",
        },
        follow_redirects=False,
    )
    assert register.status_code in {302, 303}
    assert register.headers["Location"].endswith("/login?registered=1")

    login_notice = client.get("/login?registered=1")
    assert login_notice.status_code == 200
    assert "Check your email for the verification link" in _safe_text(login_notice)

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()

    verify = client.get(f"/verify-email/{token}", follow_redirects=False)
    assert verify.status_code in {302, 303}
    assert verify.headers["Location"].endswith("/login")

    login = client.post(
        "/login",
        data={"email": "trial-owner@example.com", "password": "safe-password-123"},
        follow_redirects=False,
    )
    assert login.status_code in {302, 303}
    assert login.headers["Location"].endswith("/workbench")

    onboarding = client.get("/onboarding")
    assert onboarding.status_code == 200
    assert "Set up your workspace" in _safe_text(onboarding)

    complete_onboarding = client.post(
        "/onboarding", data={"industry": "SaaS"}, follow_redirects=False
    )
    assert complete_onboarding.status_code in {302, 303}
    assert complete_onboarding.headers["Location"].endswith("/workbench")

    with Session(engine) as session:
        tenant = session.scalars(select(Tenant)).one()
        assert tenant.onboarding_done is True
        assert tenant.industry == "SaaS"

    import_preview = client.post(
        "/leads/import",
        data={
            "action": "preview",
            "file": (
                BytesIO(
                    b"email,first_name,last_name,title,website\n"
                    b"buyer@example.com,Beth,Buyer,VP Sales,https://buyer.example\n"
                ),
                "leads.csv",
            ),
        },
        content_type="multipart/form-data",
    )
    assert import_preview.status_code == 200
    preview_text = _safe_text(import_preview)
    assert "Preview: leads.csv" in preview_text
    match = re.search(r'name="batch_id" value="([^"]+)"', preview_text)
    assert match is not None

    import_confirm = client.post(
        "/leads/import",
        data={"action": "confirm", "batch_id": match.group(1)},
    )
    assert import_confirm.status_code == 200
    assert "Imported 1 leads" in _safe_text(import_confirm)

    with Session(engine) as session:
        lead = session.scalars(select(Lead).where(Lead.email == "buyer@example.com")).one()
        lead_id = lead.id
        assert lead.source == "import"
        assert lead.status == "pending_review"

    lead_list = client.get("/leads")
    assert lead_list.status_code == 200
    assert "buyer@example.com" in _safe_text(lead_list)

    lead_detail = client.get(f"/leads/{lead_id}")
    assert lead_detail.status_code == 200
    detail_text = _safe_text(lead_detail)
    assert "buyer@example.com" in detail_text
    assert "https://buyer.example" in detail_text

    review = client.post(
        f"/leads/{lead_id}/review", data={"decision": "accepted"}, follow_redirects=False
    )
    assert review.status_code in {302, 303}

    stage = client.post(
        f"/leads/{lead_id}/stage", data={"stage": "qualified"}, follow_redirects=False
    )
    assert stage.status_code in {302, 303}

    note = client.post(
        f"/leads/{lead_id}/note",
        data={"note": "Interested in the real user trial"},
        follow_redirects=False,
    )
    assert note.status_code in {302, 303}

    updated_detail = client.get(f"/leads/{lead_id}")
    assert updated_detail.status_code == 200
    updated_text = _safe_text(updated_detail)
    assert "qualified" in updated_text
    assert "Interested in the real user trial" in updated_text

    outreach_page = client.get(f"/leads/{lead_id}/outreach")
    assert outreach_page.status_code == 200
    assert "Send to buyer@example.com" in _safe_text(outreach_page)

    send = client.post(
        f"/leads/{lead_id}/outreach/send",
        data={
            "to_email": "buyer@example.com",
            "subject": "Welcome from LeadFlow",
            "body_text": "Thanks for joining the staging acceptance test.",
        },
        follow_redirects=False,
    )
    assert send.status_code in {302, 303}
    assert send.headers["Location"].endswith(f"/leads/{lead_id}/outreach")

    sent_history = client.get(f"/leads/{lead_id}/outreach")
    assert sent_history.status_code == 200
    sent_text = _safe_text(sent_history)
    assert "Welcome from LeadFlow" in sent_text
    assert "sent" in sent_text

    dashboard = client.get("/outreach")
    assert dashboard.status_code == 200
    assert "Sent" in _safe_text(dashboard)

    with Session(engine) as session:
        saved_lead = session.get(Lead, lead_id)
        assert saved_lead is not None
        assert saved_lead.status == "accepted"
        assert saved_lead.stage == "qualified"
        assert "Interested in the real user trial" in saved_lead.notes
        message = session.scalars(
            select(OutreachMessage).where(OutreachMessage.lead_id == lead_id)
        ).one()
        assert message.status == "sent"
        actions = {
            action
            for action in session.scalars(
                select(Activity.action).where(Activity.lead_id == lead_id)
            )
        }
        assert {"imported", "accepted", "stage_changed", "note_added", "email_sent"} <= actions
