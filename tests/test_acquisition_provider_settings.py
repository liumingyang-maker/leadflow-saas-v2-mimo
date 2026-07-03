from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "acquisition-provider-test-secret-key")
    monkeypatch.setenv("TENANT_SECRET_KEY", "acquisition-provider-test-tenant-key")
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "acquisition-provider-test-outreach-key")
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
        sess["admin_id"] = "admin-test"
        sess["admin_email"] = "admin@example.com"
        sess["admin_must_change_password"] = False
    return client


def test_acquisition_provider_settings_default_disabled(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = _admin_client(app)

    response = client.get("/admin/acquisition")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "获客渠道 provider 设置" in html
    assert "disabled" in html
    assert "brave" in html


def test_admin_can_save_fake_provider_and_test_connection(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = _admin_client(app)

    response = client.post(
        "/admin/acquisition",
        data={
            "provider": "fake",
            "enabled": "1",
            "daily_spend_cap_cents": "100",
            "query_limit_per_run": "3",
            "result_limit_per_run": "10",
            "timeout_seconds": "10",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    response = client.post("/admin/acquisition", data={"action": "test"})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "获客 provider 测试成功" in html


def test_brave_key_is_encrypted_masked_and_not_overwritten(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client = _admin_client(app)
    fake_key = "brave-alpha7-test-key"

    response = client.post(
        "/admin/acquisition",
        data={
            "provider": "brave",
            "enabled": "1",
            "api_key": fake_key,
            "daily_spend_cap_cents": "100",
            "query_limit_per_run": "3",
            "result_limit_per_run": "10",
            "timeout_seconds": "10",
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    from app.modules.acquisition.models import AcquisitionProviderSettings

    assert response.status_code == 200
    assert fake_key not in html
    assert "****-key" in html
    with Session(engine) as session:
        settings = session.scalar(select(AcquisitionProviderSettings))
        assert settings is not None
        assert fake_key not in settings.api_key_encrypted
        encrypted = settings.api_key_encrypted

    client.post(
        "/admin/acquisition",
        data={
            "provider": "brave",
            "enabled": "1",
            "api_key": "",
            "daily_spend_cap_cents": "100",
            "query_limit_per_run": "3",
            "result_limit_per_run": "10",
            "timeout_seconds": "10",
        },
    )

    with Session(engine) as session:
        settings = session.scalar(select(AcquisitionProviderSettings))
        assert settings is not None
        assert settings.api_key_encrypted == encrypted
