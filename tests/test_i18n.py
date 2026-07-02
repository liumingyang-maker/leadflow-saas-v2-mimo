from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import translate
from app.i18n.en_us import TRANSLATIONS as EN_US
from app.i18n.zh_cn import TRANSLATIONS as ZH_CN

ROOT = Path(__file__).resolve().parents[1]


class RecordingMailer:
    def __init__(self) -> None:
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
        return type("Result", (), {"success": True, "error_code": "", "error_summary": ""})()


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "i18n-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "i18n-test-tenant-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
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


def _verify(client, engine) -> None:
    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
    client.get(f"/verify-email/{token}")


def test_login_defaults_to_zh_cn(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    response = app.test_client().get("/login")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'lang="zh-CN"' in html
    assert "登录 LeadFlow" in html
    assert "中文" in html
    assert "EN" in html


def test_locale_route_sets_english_cookie_and_renders_english(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = app.test_client()

    response = client.get("/locale/en-US?next=/login")
    html = client.get("/login").get_data(as_text=True)

    assert response.status_code in {302, 303}
    assert response.headers["Location"] == "/login"
    assert "lang=en-US" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    assert 'lang="en-US"' in html
    assert "Sign in to LeadFlow" in html


def test_locale_route_sets_chinese_cookie_and_renders_chinese(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = app.test_client()

    response = client.get("/locale/zh-CN?next=/login")
    html = client.get("/login").get_data(as_text=True)

    assert response.status_code in {302, 303}
    assert "lang=zh-CN" in response.headers["Set-Cookie"]
    assert 'lang="zh-CN"' in html
    assert "登录 LeadFlow" in html


def test_locale_route_rejects_open_redirect(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    response = app.test_client().get("/locale/en-US?next=https://evil.example/phish")

    assert response.status_code in {302, 303}
    assert response.headers["Location"] == "/login"


def test_missing_translation_key_falls_back_to_key(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    with app.test_request_context("/"):
        assert translate("missing.translation.key") == "missing.translation.key"


def test_verification_email_is_chinese_by_default(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)

    _register(app.test_client())

    assert mailer.messages
    assert mailer.messages[0]["subject"] == "验证你的 LeadFlow 邮箱"
    assert "请使用以下链接验证你的邮箱地址" in mailer.messages[0]["body_text"]


def test_password_reset_email_is_chinese_by_default(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, engine = _app(monkeypatch)
    client = app.test_client()
    _register(client)
    _verify(client, engine)
    mailer.messages.clear()

    client.post("/forgot-password", data={"email": "owner@example.com"})

    assert mailer.messages
    assert mailer.messages[0]["subject"] == "重置你的 LeadFlow 密码"
    assert "请使用以下链接重置你的 LeadFlow 密码" in mailer.messages[0]["body_text"]


def test_auth_email_uses_english_when_cookie_is_en_us(monkeypatch) -> None:
    mailer = RecordingMailer()
    monkeypatch.setattr("app.modules.accounts.service.get_mailer", lambda: mailer)
    app, _engine = _app(monkeypatch)
    client = app.test_client()
    client.get("/locale/en-US?next=/register")

    _register(client)

    assert mailer.messages
    assert mailer.messages[0]["subject"] == "Verify your LeadFlow email"
    assert "Verify your email address with this link" in mailer.messages[0]["body_text"]


def test_translation_key_parity_and_templates_have_no_missing_keys() -> None:
    assert set(ZH_CN) == set(EN_US)
    assert _template_translation_keys() <= set(ZH_CN)


def test_no_obvious_hardcoded_auth_navigation_button_english() -> None:
    checked = [
        ROOT / "app" / "templates" / "auth" / "login.html",
        ROOT / "app" / "templates" / "auth" / "register.html",
        ROOT / "app" / "templates" / "auth" / "forgot_password.html",
        ROOT / "app" / "templates" / "auth" / "reset_password.html",
        ROOT / "app" / "templates" / "components" / "_shell.html",
    ]
    forbidden = [
        ">Sign in",
        ">Continue<",
        ">Create tenant<",
        ">Forgot password?",
        ">New workspace?",
        ">Skip to content<",
    ]
    for template in checked:
        content = template.read_text(encoding="utf-8")
        for text in forbidden:
            assert text not in content


def _template_translation_keys() -> set[str]:
    pattern = re.compile(r"""\bt\(\s*(['"])(.*?)\1""")
    keys: set[str] = set()
    for template in (ROOT / "app" / "templates").rglob("*.html"):
        if "design_system" in template.parts:
            continue
        keys.update(match.group(2) for match in pattern.finditer(template.read_text()))
    return keys
