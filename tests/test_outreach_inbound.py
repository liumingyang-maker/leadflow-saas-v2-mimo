"""V2-05 focused acceptance tests for outreach and inbound."""

from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64encode
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch, *, csrf: bool = False):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "test-tenant-secret-key-that-is-long-enough")
    monkeypatch.setenv("INBOUND_TOKEN_KEY", "test-inbound-token-key-that-is-long-enough")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "test-outreach-signing-key-that-is-long-enough")
    import app.config as cfg
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    monkeypatch.setattr(cfg.TestingConfig, "WTF_CSRF_ENABLED", csrf)
    monkeypatch.setattr(
        cfg.TestingConfig, "INBOUND_TOKEN_KEY", "test-inbound-token-key-that-is-long-enough"
    )
    monkeypatch.setattr(
        cfg.TestingConfig, "OUTREACH_SIGNING_KEY", "test-outreach-signing-key-that-is-long-enough"
    )
    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _login_client(app, engine):
    from app.modules.accounts.models import Tenant, TenantMembership, User

    with Session(engine) as session:
        tenant = Tenant(company_name="Outreach Co")
        user = User(
            email="owner@example.com",
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
        sess["tenant_email"] = "owner@example.com"
    return client, tenant_id


def _lead(engine, tenant_id: str, email: str = "buyer@example.com") -> str:
    from app.modules.leads.models import Lead

    with Session(engine) as session:
        lead = Lead(
            tenant_id=tenant_id,
            email=email,
            first_name="Buyer",
            last_name="One",
            source="manual",
            status="accepted",
        )
        session.add(lead)
        session.commit()
        return lead.id


def _unsubscribe_token(app, tracking_id: str, email: str) -> str:
    from app.modules.outreach.service import sign_unsubscribe_token

    return sign_unsubscribe_token(app, tracking_id, email)


def test_tracking_redirect_signature_uses_configured_key(monkeypatch):
    app, _engine = _app(monkeypatch)

    from app.modules.outreach.service import sign_redirect, verify_redirect

    sig = sign_redirect(app, "track-1", "https://example.com/pricing", 1234567890)

    assert verify_redirect(app, "track-1", "https://example.com/pricing", 1234567890, sig)
    assert not verify_redirect(app, "track-1", "https://example.com/pricing", 1234567890, "bad")
    assert not verify_redirect(app, "track-1", "https://example.com/other", 1234567890, sig)


def test_unsubscribe_signature_uses_configured_key(monkeypatch):
    app, _engine = _app(monkeypatch)

    from app.modules.outreach.service import sign_unsubscribe_token, verify_unsubscribe_token

    token = sign_unsubscribe_token(app, "track-1", "Buyer@Example.com")

    assert verify_unsubscribe_token(app, token) == ("track-1", "buyer@example.com")
    assert verify_unsubscribe_token(app, token[:-2] + "xx") is None


def test_outreach_page_send_tracking_and_unsubscribe(monkeypatch):
    app, engine = _app(monkeypatch)
    client, tenant_id = _login_client(app, engine)
    lead_id = _lead(engine, tenant_id)

    page = client.get(f"/leads/{lead_id}/outreach")
    assert page.status_code == 200
    assert b"Send to buyer@example.com" in page.data

    sent = client.post(
        f"/leads/{lead_id}/outreach/send",
        data={"to_email": "buyer@example.com", "subject": "Hello", "body_text": "Hi"},
    )
    assert sent.status_code == 302

    from app.modules.leads.models import Activity
    from app.modules.outreach.models import EmailTracking, OutreachMessage, Suppression

    with Session(engine) as session:
        message = session.scalar(
            select(OutreachMessage).where(OutreachMessage.tenant_id == tenant_id)
        )
        tracking = session.scalar(select(EmailTracking).where(EmailTracking.tenant_id == tenant_id))
        activity = session.scalar(
            select(Activity).where(Activity.tenant_id == tenant_id, Activity.action == "email_sent")
        )
    assert message is not None and message.status == "sent"
    assert tracking is not None
    assert activity is not None

    token = _unsubscribe_token(app, tracking.tracking_id, "buyer@example.com")
    confirm = client.get(f"/unsubscribe/{token}")
    assert confirm.status_code == 200
    assert b"buyer@example.com" in confirm.data

    done = client.post(f"/unsubscribe/{token}")
    assert done.status_code == 200
    with Session(engine) as session:
        suppression = session.scalar(select(Suppression).where(Suppression.tenant_id == tenant_id))
    assert suppression is not None
    assert suppression.email == "buyer@example.com"


def test_tampered_unsubscribe_token_rejected(monkeypatch):
    app, engine = _app(monkeypatch)
    client, tenant_id = _login_client(app, engine)
    lead_id = _lead(engine, tenant_id)
    client.post(
        f"/leads/{lead_id}/outreach/send",
        data={"to_email": "buyer@example.com", "subject": "Hello", "body_text": "Hi"},
    )

    from app.modules.outreach.models import EmailTracking

    with Session(engine) as session:
        tracking = session.scalar(select(EmailTracking).where(EmailTracking.tenant_id == tenant_id))
    assert tracking is not None
    token = _unsubscribe_token(app, tracking.tracking_id, "other@example.com")[:-2] + "xx"
    assert client.get(f"/unsubscribe/{token}").status_code == 400


def test_inbound_token_ciphertext_uses_configured_key_and_rotates(monkeypatch):
    app, engine = _app(monkeypatch)
    _client, tenant_id = _login_client(app, engine)

    from cryptography.fernet import Fernet

    from app.modules.inbound.models import InboundToken
    from app.modules.inbound.service import generate_token, lookup_token

    first_record, first_plaintext = generate_token(app, tenant_id=tenant_id)
    second_record, second_plaintext = generate_token(app, tenant_id=tenant_id)
    key = urlsafe_b64encode(hashlib.sha256(app.config["INBOUND_TOKEN_KEY"].encode()).digest())
    fernet = Fernet(key)

    assert fernet.decrypt(first_record.token_ciphertext.encode()).decode() == first_plaintext
    assert fernet.decrypt(second_record.token_ciphertext.encode()).decode() == second_plaintext
    assert lookup_token(app, plaintext=first_plaintext) is None
    assert lookup_token(app, plaintext=second_plaintext) is not None

    with Session(engine) as session:
        first = session.get(InboundToken, first_record.id)
        second = session.get(InboundToken, second_record.id)
    assert first is not None and first.is_active is False
    assert second is not None and second.is_active is True


def test_inbound_api_origin_idempotency_and_lead_creation(monkeypatch):
    app, engine = _app(monkeypatch)
    client, tenant_id = _login_client(app, engine)

    from app.modules.inbound.service import add_origin, generate_token
    from app.modules.leads.models import Activity, Lead

    _, token = generate_token(app, tenant_id=tenant_id)
    add_origin(app, tenant_id=tenant_id, origin="https://site.example")

    blocked = client.post(
        f"/api/inbound/{token}",
        headers={"Origin": "https://evil.example"},
        content_type="application/json",
        data=json.dumps({"email": "blocked@example.com"}),
    )
    assert blocked.status_code == 403

    payload = {
        "email": "inbound@example.com",
        "name": "Inbound Buyer",
        "company": "Acme",
        "message": "Need pricing",
        "idempotency_key": "abc-123",
        "tenant_id": "forged",
    }
    first = client.post(
        f"/api/inbound/{token}",
        headers={"Origin": "https://site.example"},
        content_type="application/json",
        data=json.dumps(payload),
    )
    assert first.status_code == 200
    assert first.headers["Access-Control-Allow-Origin"] == "https://site.example"
    body = first.get_json()
    assert body["ok"] is True

    replay = client.post(
        f"/api/inbound/{token}",
        headers={"Origin": "https://site.example"},
        content_type="application/json",
        data=json.dumps(payload),
    )
    assert replay.status_code == 200
    assert replay.get_json() == first.get_json()

    conflict_payload = dict(payload)
    conflict_payload["message"] = "Different"
    conflict = client.post(
        f"/api/inbound/{token}",
        headers={"Origin": "https://site.example"},
        content_type="application/json",
        data=json.dumps(conflict_payload),
    )
    assert conflict.status_code == 409

    with Session(engine) as session:
        lead = session.scalar(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.email == "inbound@example.com")
        )
        activity = session.scalar(
            select(Activity).where(
                Activity.tenant_id == tenant_id, Activity.action == "inbound_received"
            )
        )
        blocked_count = session.scalar(
            select(func.count(Lead.id)).where(Lead.email == "blocked@example.com")
        )
    assert lead is not None
    assert lead.source == "inbound"
    assert "Acme" in lead.notes
    assert activity is not None
    assert blocked_count == 0


def test_inbound_no_key_fingerprint_replays(monkeypatch):
    app, engine = _app(monkeypatch)
    client, tenant_id = _login_client(app, engine)

    from app.modules.inbound.service import generate_token
    from app.modules.leads.models import Lead

    _, token = generate_token(app, tenant_id=tenant_id)
    payload = {"email": "fingerprint@example.com", "name": "No Key"}
    first = client.post(
        f"/api/inbound/{token}", content_type="application/json", data=json.dumps(payload)
    )
    second = client.post(
        f"/api/inbound/{token}", content_type="application/json", data=json.dumps(payload)
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json() == first.get_json()

    with Session(engine) as session:
        count = session.scalar(
            select(func.count(Lead.id)).where(Lead.email == "fingerprint@example.com")
        )
    assert count == 1


def test_browser_posts_require_real_csrf(monkeypatch):
    app, engine = _app(monkeypatch, csrf=True)
    client, tenant_id = _login_client(app, engine)
    lead_id = _lead(engine, tenant_id)

    assert client.post("/outreach/templates", data={"name": "x"}).status_code == 400
    assert client.post("/inbound/regenerate").status_code == 400
    assert (
        client.post("/inbound/origins", data={"origin": "https://site.example"}).status_code == 400
    )
    assert (
        client.post(
            f"/leads/{lead_id}/outreach/send",
            data={"to_email": "buyer@example.com", "subject": "x", "body_text": "x"},
        ).status_code
        == 400
    )

    import re

    page = client.get("/outreach/templates")
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.get_data(as_text=True))
    assert token is not None
    ok = client.post(
        "/outreach/templates",
        data={
            "csrf_token": token.group(1),
            "name": "Intro",
            "subject": "Hello",
            "body_text": "Hi",
        },
    )
    assert ok.status_code == 302
