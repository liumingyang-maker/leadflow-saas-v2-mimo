from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "ai-test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "ai-test-tenant-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _admin_client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["is_admin"] = True
        sess["admin_id"] = "admin-1"
        sess["admin_email"] = "admin@example.com"
        sess["admin_must_change_password"] = False
    return client


def _tenant_client(app, engine):
    from app.modules.accounts.models import Tenant, TenantMembership, User

    with Session(engine) as session:
        tenant = Tenant(company_name="AI Co", status="active", plan="basic")
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


def test_admin_ai_defaults_to_disabled(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    response = _admin_client(app).get("/admin/ai")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "AI 控制台" in html
    assert '<option value="disabled" selected>' in html
    assert 'id="enabled" name="enabled" type="checkbox" value="1"' in html


def test_admin_ai_saves_encrypted_key_and_shows_only_mask(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    secret = "sk-test-secret-1234"
    client = _admin_client(app)

    response = client.post(
        "/admin/ai",
        data={
            "action": "save",
            "enabled": "1",
            "provider": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "model": "mimo-test",
            "api_key": secret,
            "timeout_seconds": "20",
            "max_output_tokens": "500",
        },
    )
    page = client.get("/admin/ai").get_data(as_text=True)

    from app.core.secret_crypto import decrypt_secret
    from app.modules.ai.models import AIProviderSettings

    assert response.status_code in {302, 303}
    with Session(engine) as session:
        settings = session.scalar(select(AIProviderSettings))
    assert settings is not None
    assert settings.api_key_encrypted
    assert secret not in settings.api_key_encrypted
    assert decrypt_secret(settings.api_key_encrypted) == secret
    assert settings.api_key_last4 == "1234"
    assert secret not in page
    assert "****1234" in page


def test_fake_provider_connection_and_tenant_quota(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.ai.service import save_provider_settings, test_provider_connection

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

    ok, reason = test_provider_connection(app)
    client, _tenant_id = _tenant_client(app, engine)
    response = client.get("/ai/quota")

    assert ok is True
    assert reason == ""
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["included"] == 1000
    assert payload["used"] == 0
    assert payload["remaining"] == 1000


def test_openai_compatible_provider_posts_chat_completion(monkeypatch) -> None:
    from app.integrations.ai.base import AIGenerationRequest
    from app.integrations.ai.openai_compatible import OpenAICompatibleProvider

    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "Subject: Hello\n\nBody"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 5},
                }
            ).encode()

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode())
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleProvider(
        base_url="https://api.example.test/v1",
        model="mimo-test",
        api_key="sk-test-secret",
        timeout_seconds=12,
    )
    result = provider.generate_text(
        AIGenerationRequest(system_prompt="system", user_prompt="user", max_output_tokens=88)
    )

    assert result.success is True
    assert result.text == "Subject: Hello\n\nBody"
    assert captured["url"] == "https://api.example.test/v1/chat/completions"
    assert captured["timeout"] == 12
    assert captured["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert captured["body"]["model"] == "mimo-test"
    assert captured["body"]["max_tokens"] == 88


def test_openai_compatible_missing_config_fails_without_secret_leakage() -> None:
    from app.integrations.ai.base import AIGenerationRequest
    from app.integrations.ai.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url="",
        model="mimo-test",
        api_key="",
    )
    result = provider.generate_text(AIGenerationRequest(system_prompt="system", user_prompt="user"))

    assert result.success is False
    assert result.error_code in {"missing_api_key", "provider_not_configured"}
    assert "sk-" not in result.error_summary
