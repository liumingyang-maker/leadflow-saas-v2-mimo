from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session


class RecordingMailer:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.messages = []

    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str):
        self.messages.append(
            {
                "to_email": to_email,
                "subject": subject,
                "body_text": body_text,
                "body_html": body_html,
            }
        )
        return type(
            "Result",
            (),
            {
                "success": self.success,
                "error_code": "" if self.success else "mailer_not_configured",
                "error_summary": "" if self.success else "Email sending is not configured",
            },
        )()


def _client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)

    return flask_app.test_client(), engine


def test_register_sends_verification_email(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, engine = _client(monkeypatch)

    response = client.post(
        "/register",
        data={
            "email": "Owner@Example.com ",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    from app.modules.accounts.models import EmailToken

    assert response.status_code in {302, 303}
    with Session(engine) as session:
        token = session.scalars(select(EmailToken.token)).one()
    assert len(mailer.messages) == 1
    message = mailer.messages[0]
    assert message["to_email"] == "owner@example.com"
    assert "Verify" in message["subject"]
    assert f"/verify-email/{token}" in message["body_text"]


def test_register_reports_verification_email_failure(monkeypatch) -> None:
    mailer = RecordingMailer(success=False)
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, _engine = _client(monkeypatch)

    response = client.post(
        "/register",
        data={
            "email": "Owner@Example.com ",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    assert response.status_code == 400
    assert "Verification email could not be sent" in response.get_data(as_text=True)


def test_register_creates_unverified_owner_tenant_and_token(monkeypatch) -> None:
    client, engine = _client(monkeypatch)

    response = client.post(
        "/register",
        data={
            "email": "Owner@Example.com ",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    from app.modules.accounts.models import EmailToken, Tenant, TenantMembership, User

    assert response.status_code in {302, 303}
    assert response.headers["Location"].startswith("/login")
    with Session(engine) as session:
        user = session.scalars(select(User)).one()
        tenant = session.scalars(select(Tenant)).one()
        membership = session.scalars(select(TenantMembership)).one()
        token = session.scalars(select(EmailToken)).one()

        assert user.email == "owner@example.com"
        assert user.password_hash != "safe-password-123"
        assert user.email_verified_at is None
        assert tenant.company_name == "Acme Export"
        assert tenant.status == "trial"
        assert membership.role == "owner"
        assert membership.tenant_id == tenant.id
        assert membership.user_id == user.id
        assert token.token_type == "verify"
        assert token.used_at is None


def test_login_requires_verified_email_and_rotates_session(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    with client.session_transaction() as sess:
        sess["tenant_id"] = "old-tenant"
        sess["is_admin"] = True

    blocked = client.post(
        "/login", data={"email": "owner@example.com", "password": "safe-password-123"}
    )
    assert blocked.status_code == 200
    assert "Email verification required" in blocked.get_data(as_text=True)

    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(select(EmailToken.token)).one()

    verified = client.get(f"/verify-email/{token}")
    assert verified.status_code in {302, 303}
    assert verified.headers["Location"].endswith("/login")

    logged_in = client.post(
        "/login", data={"email": "owner@example.com", "password": "safe-password-123"}
    )
    assert logged_in.status_code in {302, 303}
    assert logged_in.headers["Location"].endswith("/workbench")
    with client.session_transaction() as sess:
        assert sess["tenant_email"] == "owner@example.com"
        assert "tenant_id" in sess
        assert "user_id" in sess
        assert "is_admin" not in sess
        assert sess.permanent is True


def test_login_rate_limits_failed_attempts(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(select(EmailToken.token)).one()
    client.get(f"/verify-email/{token}")

    for _ in range(5):
        response = client.post(
            "/login",
            data={"email": "owner@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 200

    limited = client.post(
        "/login",
        data={"email": "owner@example.com", "password": "safe-password-123"},
    )

    assert limited.status_code == 429


def test_register_rate_limits_repeated_attempts(monkeypatch) -> None:
    client, _engine = _client(monkeypatch)

    for _ in range(5):
        response = client.post(
            "/register",
            data={"email": "bad@example.com", "password": "short", "company_name": "Acme"},
        )
        assert response.status_code == 400

    limited = client.post(
        "/register",
        data={"email": "bad@example.com", "password": "short", "company_name": "Acme"},
    )

    assert limited.status_code == 429


def test_email_verification_token_is_single_use(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(select(EmailToken.token)).one()

    first = client.get(f"/verify-email/{token}")
    second = client.get(f"/verify-email/{token}")

    assert first.status_code in {302, 303}
    assert second.status_code == 400


def test_email_verification_expired_or_forged_token_is_rejected(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )

    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(select(EmailToken).where(EmailToken.token_type == "verify")).one()
        token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        token_id = token.token

    expired = client.get(f"/verify-email/{token_id}")
    forged = client.get("/verify-email/not-a-real-token")

    assert expired.status_code == 400
    assert forged.status_code == 400


def test_logout_clears_tenant_session(monkeypatch) -> None:
    client, _engine = _client(monkeypatch)
    with client.session_transaction() as sess:
        sess["tenant_id"] = "tenant"
        sess["tenant_email"] = "owner@example.com"
        sess["user_id"] = "user"

    response = client.post("/logout")

    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert "tenant_id" not in sess
        assert "tenant_email" not in sess
        assert "user_id" not in sess
