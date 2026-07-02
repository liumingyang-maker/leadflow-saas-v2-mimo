from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session


class RecordingMailer:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.messages: list[dict[str, str]] = []

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


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "resend-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "resend-test-tenant-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    flask_app.config["ACCOUNT_EMAIL_BASE_URL"] = "https://huokeradar.com"
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _register(client, email: str = "owner@example.com") -> None:
    client.post(
        "/register",
        data={
            "email": email,
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )


def _verify(client, engine, email: str = "owner@example.com") -> None:
    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(
                EmailToken.email == email,
                EmailToken.token_type == "verify",
            )
        ).one()
    client.get(f"/verify-email/{token}")


def _verify_tokens(engine, email: str = "owner@example.com"):
    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        return session.scalars(
            select(EmailToken)
            .where(EmailToken.email == email, EmailToken.token_type == "verify")
            .order_by(EmailToken.created_at)
        ).all()


def _reset_tokens(engine, email: str = "owner@example.com"):
    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        return session.scalars(
            select(EmailToken).where(EmailToken.email == email, EmailToken.token_type == "reset")
        ).all()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def test_resend_verification_page_defaults_to_zh_cn(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)

    response = app.test_client().get("/resend-verification")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'lang="zh-CN"' in html
    assert "重新发送验证邮件" in html
    assert "输入邮箱以接收新的验证链接。" in html
    assert "中文" in html
    assert "EN" in html


def test_resend_verification_language_toggle_uses_english(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = app.test_client()

    client.get("/locale/en-US?next=/resend-verification")
    response = client.get("/resend-verification")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'lang="en-US"' in html
    assert "Resend verification email" in html
    assert "Enter your email to receive a new verification link." in html


def test_resend_verification_unknown_email_returns_generic_message(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)

    response = app.test_client().post("/resend-verification", data={"email": "missing@example.com"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "如果该邮箱存在且尚未验证，我们会重新发送验证邮件" in html
    assert mailer.messages == []


def test_resend_verification_already_verified_returns_generic_without_email(
    monkeypatch,
) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, engine = _app(monkeypatch)
    client = app.test_client()
    _register(client)
    _verify(client, engine)
    mailer.messages.clear()

    response = client.post("/resend-verification", data={"email": "owner@example.com"})

    assert response.status_code == 200
    assert "如果该邮箱存在且尚未验证，我们会重新发送验证邮件" in response.get_data(as_text=True)
    assert mailer.messages == []


def test_resend_verification_generates_new_token_and_invalidates_old_token(
    monkeypatch,
) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, engine = _app(monkeypatch)
    client = app.test_client()
    _register(client)
    old_token = _verify_tokens(engine)[0]
    old_token_id = old_token.token
    mailer.messages.clear()

    response = client.post("/resend-verification", data={"email": "owner@example.com"})

    tokens = _verify_tokens(engine)
    old_token = tokens[0]
    new_token = tokens[1]
    assert response.status_code == 200
    assert len(tokens) == 2
    assert old_token.used_at is not None
    assert _as_utc(old_token.expires_at) <= datetime.now(UTC)
    assert new_token.used_at is None
    assert new_token.token != old_token_id
    assert (
        timedelta(hours=23, minutes=59)
        <= _as_utc(new_token.expires_at) - datetime.now(UTC)
        <= timedelta(hours=24, seconds=5)
    )
    assert len(mailer.messages) == 1
    assert mailer.messages[0]["to_email"] == "owner@example.com"
    assert (
        f"https://huokeradar.com/verify-email/{new_token.token}" in mailer.messages[0]["body_text"]
    )

    old_response = client.get(f"/verify-email/{old_token_id}")
    new_response = client.get(f"/verify-email/{new_token.token}")

    assert old_response.status_code == 400
    assert new_response.status_code in {302, 303}


def test_register_verify_token_is_24_hours_and_reset_token_remains_30_minutes(
    monkeypatch,
) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, engine = _app(monkeypatch)
    client = app.test_client()
    before_register = datetime.now(UTC)
    _register(client)
    verify_token = _verify_tokens(engine)[0]

    assert (
        timedelta(hours=23, minutes=59)
        <= _as_utc(verify_token.expires_at) - before_register
        <= (timedelta(hours=24, seconds=5))
    )

    _verify(client, engine)
    before_reset = datetime.now(UTC)
    client.post("/forgot-password", data={"email": "owner@example.com"})
    reset_token = _reset_tokens(engine)[0]

    assert (
        timedelta(minutes=29)
        <= _as_utc(reset_token.expires_at) - before_reset
        <= timedelta(minutes=30, seconds=5)
    )


def test_resend_verification_rate_limit_keeps_generic_response(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)
    client = app.test_client()
    _register(client)
    mailer.messages.clear()

    first = client.post("/resend-verification", data={"email": "owner@example.com"})
    second = client.post("/resend-verification", data={"email": "owner@example.com"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert "如果该邮箱存在且尚未验证，我们会重新发送验证邮件" in first.get_data(as_text=True)
    assert "如果该邮箱存在且尚未验证，我们会重新发送验证邮件" in second.get_data(as_text=True)
    assert len(mailer.messages) == 1


def test_resend_verification_responses_do_not_enumerate_account_state(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, engine = _app(monkeypatch)
    client = app.test_client()
    _register(client, "unverified@example.com")
    _register(client, "verified@example.com")
    _verify(client, engine, "verified@example.com")
    mailer.messages.clear()

    missing = client.post("/resend-verification", data={"email": "missing@example.com"})
    verified = client.post("/resend-verification", data={"email": "verified@example.com"})
    unverified = client.post("/resend-verification", data={"email": "unverified@example.com"})

    generic = "如果该邮箱存在且尚未验证，我们会重新发送验证邮件"
    assert {missing.status_code, verified.status_code, unverified.status_code} == {200}
    assert generic in missing.get_data(as_text=True)
    assert generic in verified.get_data(as_text=True)
    assert generic in unverified.get_data(as_text=True)


def test_resend_verification_email_uses_chinese_by_default(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)
    client = app.test_client()
    _register(client)
    mailer.messages.clear()

    client.post("/resend-verification", data={"email": "owner@example.com"})

    assert mailer.messages
    assert mailer.messages[0]["subject"] == "验证你的 LeadFlow 邮箱"
    assert "请使用以下链接验证你的邮箱地址" in mailer.messages[0]["body_text"]
    assert "24 小时" in mailer.messages[0]["body_text"]


def test_resend_verification_email_uses_english_with_en_us_cookie(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)
    client = app.test_client()
    client.get("/locale/en-US?next=/register")
    _register(client)
    mailer.messages.clear()

    client.post("/resend-verification", data={"email": "owner@example.com"})

    assert mailer.messages
    assert mailer.messages[0]["subject"] == "Verify your LeadFlow email"
    assert "Verify your email address with this link" in mailer.messages[0]["body_text"]
    assert "24 hours" in mailer.messages[0]["body_text"]


def test_resend_verification_hides_smtp_failure(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)
    client = app.test_client()
    _register(client)
    failing_mailer = RecordingMailer(success=False)
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: failing_mailer)

    response = client.post("/resend-verification", data={"email": "owner@example.com"})

    assert response.status_code == 200
    assert "如果该邮箱存在且尚未验证，我们会重新发送验证邮件" in response.get_data(as_text=True)
    assert len(failing_mailer.messages) == 1
