from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash


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

    client = flask_app.test_client()
    client.get("/locale/en-US?next=/login")
    return client, engine


def _verified_account(client, engine):
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
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
    client.get(f"/verify-email/{token}")


def test_forgot_password_uses_generic_response_and_creates_token_for_known_email(
    monkeypatch,
) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    mailer.messages.clear()

    known = client.post("/forgot-password", data={"email": "owner@example.com"})
    unknown = client.post("/forgot-password", data={"email": "missing@example.com"})

    from app.modules.accounts.models import EmailToken

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert "If the email exists" in known.get_data(as_text=True)
    assert "If the email exists" in unknown.get_data(as_text=True)
    with Session(engine) as session:
        reset_tokens = session.scalars(
            select(EmailToken).where(EmailToken.token_type == "reset")
        ).all()
        assert len(reset_tokens) == 1
        assert reset_tokens[0].email == "owner@example.com"
        token = reset_tokens[0].token
    assert len(mailer.messages) == 1
    assert mailer.messages[0]["to_email"] == "owner@example.com"
    assert "Reset" in mailer.messages[0]["subject"]
    assert f"/reset-password/{token}" in mailer.messages[0]["body_text"]


def test_forgot_password_hides_mailer_failure_for_existing_email(monkeypatch) -> None:
    mailer = RecordingMailer(success=False)
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    mailer.messages.clear()

    response = client.post("/forgot-password", data={"email": "owner@example.com"})

    assert response.status_code == 200
    assert "If the email exists" in response.get_data(as_text=True)
    assert len(mailer.messages) == 1


def test_forgot_password_hides_mailer_failure_for_missing_email(monkeypatch) -> None:
    mailer = RecordingMailer(success=False)
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    mailer.messages.clear()

    response = client.post("/forgot-password", data={"email": "missing@example.com"})

    assert response.status_code == 200
    assert "If the email exists" in response.get_data(as_text=True)
    assert mailer.messages == []


def test_forgot_password_rate_limit_is_non_enumerating_for_existing_email(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    mailer.messages.clear()

    responses = [
        client.post("/forgot-password", data={"email": "owner@example.com"}) for _ in range(6)
    ]

    assert {response.status_code for response in responses} == {200}
    assert all("If the email exists" in response.get_data(as_text=True) for response in responses)


def test_forgot_password_rate_limit_is_non_enumerating_for_missing_email(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    mailer.messages.clear()

    responses = [
        client.post("/forgot-password", data={"email": "missing@example.com"}) for _ in range(6)
    ]

    assert {response.status_code for response in responses} == {200}
    assert all("If the email exists" in response.get_data(as_text=True) for response in responses)
    assert mailer.messages == []


def test_reset_password_consumes_token_and_invalidates_old_password(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    client.post("/forgot-password", data={"email": "owner@example.com"})

    from app.modules.accounts.models import EmailToken, User

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "reset")
        ).one()

    reset = client.post(f"/reset-password/{token}", data={"password": "new-safe-password-456"})
    reused = client.post(f"/reset-password/{token}", data={"password": "another-safe-password-789"})

    assert reset.status_code in {302, 303}
    assert reused.status_code == 400
    with Session(engine) as session:
        user = session.scalars(select(User).where(User.email == "owner@example.com")).one()
        consumed = session.get(EmailToken, token)
        assert consumed is not None
        assert consumed.used_at is not None
        assert check_password_hash(user.password_hash, "new-safe-password-456")
        assert not check_password_hash(user.password_hash, "safe-password-123")

    old_login = client.post(
        "/login", data={"email": "owner@example.com", "password": "safe-password-123"}
    )
    new_login = client.post(
        "/login", data={"email": "owner@example.com", "password": "new-safe-password-456"}
    )
    assert old_login.status_code == 200
    assert new_login.status_code in {302, 303}


def test_reset_password_expired_or_forged_token_is_rejected(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)
    client.post("/forgot-password", data={"email": "owner@example.com"})

    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(select(EmailToken).where(EmailToken.token_type == "reset")).one()
        token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        token_id = token.token

    expired = client.post(f"/reset-password/{token_id}", data={"password": "new-safe-password-456"})
    forged = client.post(
        "/reset-password/not-a-real-token", data={"password": "new-safe-password-456"}
    )

    assert expired.status_code == 400
    assert forged.status_code == 400


def test_login_rotates_auth_session_marker(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    _verified_account(client, engine)

    with client.session_transaction() as sess:
        sess["auth_session_id"] = "stale"
        sess["tenant_id"] = "old-tenant"
        sess["is_admin"] = True

    response = client.post(
        "/login", data={"email": "owner@example.com", "password": "safe-password-123"}
    )

    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess["auth_session_id"] != "stale"
        assert sess["tenant_email"] == "owner@example.com"
        assert "is_admin" not in sess
