from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _register_and_login(client, engine) -> str:
    from app.modules.accounts.models import EmailToken, Tenant

    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
        },
    )
    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
        tenant_id = session.scalars(select(Tenant.id)).one()
    client.get(f"/verify-email/{token}")
    client.post("/login", data={"email": "owner@example.com", "password": "safe-password-123"})
    return tenant_id


def test_javascript_website_does_not_render_unsafe_href(monkeypatch) -> None:
    flask_app, engine = _app(monkeypatch)
    client = flask_app.test_client()
    tenant_id = _register_and_login(client, engine)

    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(
            Lead(
                tenant_id=tenant_id,
                email="unsafe-url@example.com",
                website="javascript:alert(1)",
            ),
            tenant_id=tenant_id,
        )
        session.commit()
        lead_id = lead.id

    response = client.get(f"/leads/{lead_id}")
    html = response.get_data(as_text=True).lower()

    assert response.status_code == 200
    assert 'href="javascript:' not in html
    assert "javascript:alert(1)" in html


def test_http_website_still_renders_safe_href(monkeypatch) -> None:
    flask_app, engine = _app(monkeypatch)
    client = flask_app.test_client()
    tenant_id = _register_and_login(client, engine)

    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(
            Lead(
                tenant_id=tenant_id,
                email="safe-url@example.com",
                website="https://example.com",
            ),
            tenant_id=tenant_id,
        )
        session.commit()
        lead_id = lead.id

    response = client.get(f"/leads/{lead_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="https://example.com"' in html


def test_unsafe_tag_color_is_sanitized(monkeypatch) -> None:
    flask_app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead, Tag
    from app.modules.leads.service import add_tag, confirm_import

    confirm_import(
        flask_app,
        tenant_id="t1",
        filename="leads.csv",
        content=b"email\nlead@example.com",
    )
    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    add_tag(
        flask_app,
        tenant_id="t1",
        lead_id=lead_id,
        tag_name="Unsafe",
        tag_color="#fff; background:url(javascript:alert(1))",
    )

    with Session(engine) as session:
        tag = session.scalars(select(Tag)).one()
        assert tag.color == "#246BFD"
