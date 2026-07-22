"""Tests for V2-03-005 through V2-03-010: service layer integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
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


# ---------------------------------------------------------------------------
# V2-03-005: Import preview and confirm
# ---------------------------------------------------------------------------


def _csv_bytes(header: str, *rows: str) -> bytes:
    return (header + "\n" + "\n".join(rows)).encode("utf-8")


def test_import_preview_does_not_write_to_db(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.service import preview_import

    result = preview_import(
        app, filename="leads.csv", content=_csv_bytes("email,name", "a@a.com,Alice")
    )
    assert result.valid_rows == 1

    from app.modules.leads.models import Lead

    with Session(engine) as session:
        assert session.scalar(select(Lead)) is None


def test_confirm_import_creates_leads(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.service import confirm_import

    count = confirm_import(
        app,
        tenant_id="t1",
        filename="leads.csv",
        content=_csv_bytes(
            "email,first_name,last_name", "a@a.com,Alice,Smith", "b@b.com,Bob,Jones"
        ),
    )
    assert count == 2

    from app.modules.leads.models import Lead

    with Session(engine) as session:
        leads = list(session.scalars(select(Lead)))
        assert len(leads) == 2
        assert leads[0].source == "import"
        assert leads[0].status == "pending_review"


def test_confirm_import_skips_duplicates(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.service import confirm_import

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "dup@x.com")
    )
    count = confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "dup@x.com")
    )
    assert count == 0

    from app.modules.leads.models import Lead

    with Session(engine) as session:
        assert session.scalar(select(Lead)) is not None


# ---------------------------------------------------------------------------
# V2-03-006: Lead review
# ---------------------------------------------------------------------------


def test_review_accept_lead(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import confirm_import, review_lead

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "lead@x.com")
    )

    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    reviewed = review_lead(
        app, tenant_id="t1", lead_id=lead_id, decision="accepted", reviewed_by="user"
    )
    assert reviewed.status == "accepted"

    from app.modules.leads.models import Activity

    with Session(engine) as session:
        activities = session.scalars(select(Activity)).all()
        assert any(a.action == "accepted" for a in activities)
        assert any(a.action == "imported" for a in activities)


def test_review_rejects_invalid_decision(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    from app.modules.leads.service import LeadServiceError, review_lead

    with pytest.raises(LeadServiceError):
        review_lead(app, tenant_id="t1", lead_id="x", decision="invalid")


# ---------------------------------------------------------------------------
# V2-03-007: CRM stage, notes, tags, follow-up
# ---------------------------------------------------------------------------


def test_change_stage(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import change_stage, confirm_import

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "lead@x.com")
    )
    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    changed = change_stage(app, tenant_id="t1", lead_id=lead_id, stage="qualified")
    assert changed.stage == "qualified"

    from app.modules.leads.models import Activity

    with Session(engine) as session:
        activities = session.scalars(select(Activity)).all()
        assert any(a.action == "stage_changed" for a in activities)


def test_add_note(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import add_note, confirm_import

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "lead@x.com")
    )
    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    lead = add_note(app, tenant_id="t1", lead_id=lead_id, note="Called client — interested")
    assert "Called client" in lead.notes


def test_set_follow_up(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import confirm_import, set_follow_up

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "lead@x.com")
    )
    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    future = datetime.now(UTC) + timedelta(days=3)
    lead = set_follow_up(app, tenant_id="t1", lead_id=lead_id, follow_up_at=future)
    assert lead.follow_up_at is not None


def test_add_and_remove_tag(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead, Tag
    from app.modules.leads.service import add_tag, confirm_import, remove_tag

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "lead@x.com")
    )
    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    add_tag(app, tenant_id="t1", lead_id=lead_id, tag_name="VIP")
    add_tag(app, tenant_id="t1", lead_id=lead_id, tag_name="VIP")  # idempotent

    with Session(engine) as session:
        tags = session.scalars(select(Tag)).all()
        assert len(tags) == 1
        assert tags[0].name == "VIP"

    # Remove tag
    remove_tag(app, tenant_id="t1", lead_id=lead_id, tag_id=tags[0].id)
    with Session(engine) as session:
        from app.modules.leads.models import LeadTagAssociation

        assocs = session.scalars(select(LeadTagAssociation)).all()
        assert len(assocs) == 0


# ---------------------------------------------------------------------------
# V2-03-008: Activity timeline
# ---------------------------------------------------------------------------


def test_get_timeline(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import confirm_import, get_timeline, review_lead

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "lead@x.com")
    )
    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()

    review_lead(app, tenant_id="t1", lead_id=lead_id, decision="accepted")

    timeline = get_timeline(app, tenant_id="t1", lead_id=lead_id)
    assert len(timeline) >= 2
    assert any(a.action == "imported" for a in timeline)
    assert any(a.action == "accepted" for a in timeline)


# ---------------------------------------------------------------------------
# V2-03-010: Bulk operations
# ---------------------------------------------------------------------------


def test_bulk_change_stage(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import bulk_change_stage, confirm_import

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "a@x.com", "b@x.com")
    )
    with Session(engine) as session:
        lead_ids = session.scalars(select(Lead.id)).all()

    count = bulk_change_stage(app, tenant_id="t1", lead_ids=lead_ids, stage="contacted")
    assert count == 2

    with Session(engine) as session:
        leads = session.scalars(select(Lead)).all()
        assert all(lead.stage == "contacted" for lead in leads)


def test_bulk_delete(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import bulk_delete, confirm_import

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "a@x.com")
    )
    with Session(engine) as session:
        lead_ids = session.scalars(select(Lead.id)).all()

    count = bulk_delete(app, tenant_id="t1", lead_ids=lead_ids)
    assert count == 1

    with Session(engine) as session:
        assert session.scalar(select(Lead)) is None


def test_bulk_rejects_too_many(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    from app.modules.leads.service import BULK_LIMIT, LeadServiceError, bulk_change_stage

    with pytest.raises(LeadServiceError, match="limited"):
        bulk_change_stage(app, tenant_id="t1", lead_ids=["x"] * (BULK_LIMIT + 1), stage="won")


# ---------------------------------------------------------------------------
# Tenant isolation across all operations
# ---------------------------------------------------------------------------


def test_service_operations_are_tenant_scoped(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import (
        LeadServiceError,
        confirm_import,
        review_lead,
    )

    confirm_import(
        app, tenant_id="t1", filename="leads.csv", content=_csv_bytes("email", "a@t1.com")
    )
    confirm_import(
        app, tenant_id="t2", filename="leads.csv", content=_csv_bytes("email", "b@t2.com")
    )

    with Session(engine) as session:
        t1_lead_id = session.scalars(select(Lead.id).where(Lead.tenant_id == "t1")).one()

    # Tenant 2 cannot review tenant 1's lead
    with pytest.raises(LeadServiceError, match="not found"):
        review_lead(app, tenant_id="t2", lead_id=t1_lead_id, decision="accepted")
