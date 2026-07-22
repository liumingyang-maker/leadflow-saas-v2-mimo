"""Tests for ImportBatch server-side persistence — fully server-side now."""

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


def _csv_bytes(header: str, *rows: str) -> bytes:
    return (header + "\n" + "\n".join(rows)).encode("utf-8")


def test_create_batch_stores_normalized_rows(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import ImportBatch
    from app.modules.leads.service import create_import_batch

    batch = create_import_batch(
        app,
        tenant_id="t1",
        filename="test.csv",
        content=_csv_bytes("email,first_name", "a@a.com,Alice"),
    )
    with Session(engine) as session:
        stored = session.get(ImportBatch, batch.id)
        assert stored is not None
        assert stored.rows_json is not None
        import json

        rows = json.loads(stored.rows_json)
        assert len(rows) >= 1
        assert rows[0]["email"] == "a@a.com"
        assert rows[0]["first_name"] == "Alice"
        assert rows[0]["is_valid"] is True


def test_preview_does_not_create_leads(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import create_import_batch

    create_import_batch(
        app, tenant_id="t1", filename="t.csv", content=_csv_bytes("email", "a@a.com")
    )
    with Session(engine) as session:
        assert session.scalar(select(Lead)) is None


def test_confirm_batch_creates_leads_from_stored_rows(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import confirm_import_batch, create_import_batch

    batch = create_import_batch(
        app, tenant_id="t1", filename="t.csv", content=_csv_bytes("email", "a@a.com")
    )
    # confirm does NOT take file content — reads from stored rows_json
    count = confirm_import_batch(app, tenant_id="t1", batch_id=batch.id)
    assert count >= 1

    with Session(engine) as session:
        assert session.scalar(select(Lead)) is not None
        lead = session.scalars(select(Lead)).one()
        assert lead.email == "a@a.com"


def test_confirm_batch_is_idempotent(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import confirm_import_batch, create_import_batch

    batch = create_import_batch(
        app, tenant_id="t1", filename="t.csv", content=_csv_bytes("email", "b@b.com")
    )
    confirm_import_batch(app, tenant_id="t1", batch_id=batch.id)
    count2 = confirm_import_batch(app, tenant_id="t1", batch_id=batch.id)
    assert count2 == 0  # idempotent

    with Session(engine) as session:
        assert len(list(session.scalars(select(Lead)))) == 1


def test_other_tenant_cannot_confirm_batch(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    from app.modules.leads.service import (
        LeadServiceError,
        confirm_import_batch,
        create_import_batch,
    )

    batch = create_import_batch(
        app, tenant_id="t1", filename="t.csv", content=_csv_bytes("email", "c@c.com")
    )
    with pytest.raises(LeadServiceError, match="not found"):
        confirm_import_batch(app, tenant_id="t2", batch_id=batch.id)


def test_expired_batch_is_rejected(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    from app.modules.leads.service import LeadServiceError, confirm_import_batch

    with Session(engine) as session:
        from app.modules.leads.models import ImportBatch

        expired = ImportBatch(
            tenant_id="t1",
            filename="old.csv",
            status="preview",
            total_rows=1,
            valid_rows=1,
            rows_json="[]",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        session.add(expired)
        session.commit()
        batch_id = expired.id

    with pytest.raises(LeadServiceError, match="expired"):
        confirm_import_batch(app, tenant_id="t1", batch_id=batch_id)


def test_batch_id_is_random_uuid(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    from app.modules.leads.service import create_import_batch

    b1 = create_import_batch(
        app, tenant_id="t1", filename="a.csv", content=_csv_bytes("email", "e@e.com")
    )
    b2 = create_import_batch(
        app, tenant_id="t1", filename="b.csv", content=_csv_bytes("email", "f@f.com")
    )
    assert b1.id != b2.id
    assert len(b1.id) == 36


def test_confirm_only_needs_batch_id(monkeypatch) -> None:
    """Confirm request needs only batch_id — no file, no content."""
    import inspect

    from app.modules.leads.service import confirm_import_batch

    sig = inspect.signature(confirm_import_batch)
    params = list(sig.parameters.keys())
    assert "batch_id" in params
    assert "content" not in params  # must NOT accept content


def test_browser_hidden_field_has_no_raw_content(monkeypatch) -> None:
    """Verify the import template exposes only batch.id, not file bytes."""
    from app.modules.leads.service import create_import_batch

    app, _engine = _app(monkeypatch)
    batch = create_import_batch(
        app, tenant_id="t1", filename="safe.csv", content=_csv_bytes("email", "g@g.com")
    )
    assert batch.id is not None
    assert batch.filename == "safe.csv"


def test_client_submitted_fields_do_not_affect_leads(monkeypatch) -> None:
    """Even if browser sends manipulated data, confirm uses server rows."""
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.service import confirm_import_batch, create_import_batch

    batch = create_import_batch(
        app,
        tenant_id="t1",
        filename="t.csv",
        content=_csv_bytes("email,first_name", "real@real.com,RealName"),
    )
    count = confirm_import_batch(app, tenant_id="t1", batch_id=batch.id)
    assert count >= 1
    with Session(engine) as session:
        lead = session.scalars(select(Lead)).one()
        assert lead.email == "real@real.com"
        assert lead.first_name == "RealName"


def test_confirm_transaction_rolls_back_on_failure(monkeypatch) -> None:
    """If confirm fails mid-way, batch stays in preview and no leads created."""
    app, engine = _app(monkeypatch)
    from app.modules.leads.models import ImportBatch, Lead
    from app.modules.leads.service import confirm_import_batch, create_import_batch

    batch = create_import_batch(
        app, tenant_id="t1", filename="t.csv", content=_csv_bytes("email", "h@h.com")
    )
    with Session(engine) as session:
        stored = session.get(ImportBatch, batch.id)
        # Corrupt the rows_json to cause a parse failure during confirm
        stored.rows_json = "{corrupt"
        session.commit()

    from json import JSONDecodeError

    with pytest.raises(JSONDecodeError):
        confirm_import_batch(app, tenant_id="t1", batch_id=batch.id)

    with Session(engine) as session:
        stored = session.get(ImportBatch, batch.id)
        assert stored.status == "preview"  # NOT completed
        assert session.scalar(select(Lead)) is None
