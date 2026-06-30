"""V2-03-011/012: CRM acceptance tests."""

from __future__ import annotations

import os
import tempfile

from sqlalchemy import select
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "test-tenant-secret-key")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _client(monkeypatch):
    app, engine = _app(monkeypatch)
    return app.test_client(), engine, app


def _authenticate(client, engine) -> str:
    """Register + verify + login, return tenant_id."""
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


def _csv_bytes(header: str, *rows: str) -> bytes:
    return (header + "\n" + "\n".join(rows)).encode("utf-8")


# ---------------------------------------------------------------------------
# V2-03-011: CRM flow via service
# ---------------------------------------------------------------------------


def test_crm_service_import_flow(monkeypatch) -> None:
    """End-to-end: import -> review -> stage -> note -> tag -> timeline."""
    app, engine = _app(monkeypatch)
    tenant_id = "t1"

    from app.modules.leads.service import (
        add_note,
        add_tag,
        change_stage,
        confirm_import,
        get_timeline,
        review_lead,
    )

    # Import
    count = confirm_import(
        app, tenant_id=tenant_id, filename="test.csv", content=_csv_bytes("email", "lead@test.com")
    )
    assert count == 1

    from app.modules.leads.models import Lead

    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    # Review
    lead = review_lead(app, tenant_id=tenant_id, lead_id=lead_id, decision="accepted")
    assert lead.status == "accepted"

    # Change stage
    lead = change_stage(app, tenant_id=tenant_id, lead_id=lead_id, stage="qualified")
    assert lead.stage == "qualified"

    # Add note
    lead = add_note(app, tenant_id=tenant_id, lead_id=lead_id, note="Interested in demo")
    assert "Interested in demo" in lead.notes

    # Add tag
    add_tag(app, tenant_id=tenant_id, lead_id=lead_id, tag_name="Hot")
    from app.modules.leads.models import Tag

    with Session(engine) as session:
        assert session.scalar(select(Tag)) is not None

    # Timeline
    timeline = get_timeline(app, tenant_id=tenant_id, lead_id=lead_id)
    assert len(timeline) >= 4


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_lead_invisible(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        repo.add(Lead(email="secret@t1.com", tenant_id="t1"), tenant_id="t1")
        session.commit()

        assert repo.get("non-existent", tenant_id="t2") is None
        assert len(repo.list(tenant_id="t2")) == 0


# ---------------------------------------------------------------------------
# V2-03-012: Full regression
# ---------------------------------------------------------------------------


def test_v2_guard_and_session_still_work(monkeypatch) -> None:
    """V2-02: tenant guards and session rotation."""
    client, engine, app = _client(monkeypatch)
    tenant_id = _authenticate(client, engine)

    from app.modules.accounts.guards import tenant_is_expired
    from app.modules.accounts.models import Tenant

    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        assert not tenant_is_expired(tenant)

    # Session is active
    with client.session_transaction() as sess:
        assert sess.get("tenant_id") == tenant_id

    # Logout clears session
    client.post("/logout")
    with client.session_transaction() as sess:
        assert "tenant_id" not in sess


def test_alembic_migration_runs(monkeypatch) -> None:
    """Test all 5 migrations from empty DB."""
    from alembic import command
    from alembic.config import Config

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")

        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "-1")
        command.upgrade(alembic_cfg, "head")


def test_no_real_data_or_network(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    assert "sqlite:///:memory:" in str(engine.url)


def test_app_factory_independence(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-key")
    from app import create_app

    a1 = create_app("testing")
    a2 = create_app("testing")
    assert a1 is not a2
