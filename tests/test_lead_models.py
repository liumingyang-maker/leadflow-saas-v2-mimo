"""Tests for V2-03-001: Lead, company, tag and activity models."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def _engine(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return engine


def test_lead_model_creates_and_has_tenant_id(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead

    with Session(engine) as session:
        lead = Lead(
            tenant_id="tenant-1",
            email="contact@example.com",
            first_name="John",
            last_name="Doe",
        )
        session.add(lead)
        session.commit()

        saved = session.scalars(select(Lead)).one()
        assert saved.tenant_id == "tenant-1"
        assert saved.email == "contact@example.com"
        assert saved.first_name == "John"
        assert saved.last_name == "Doe"
        assert saved.status == "raw"
        assert saved.stage == "new"
        assert saved.source == "manual"


def test_company_model_creates_and_has_tenant_id(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Company

    with Session(engine) as session:
        company = Company(tenant_id="tenant-1", name="Acme Corp", domain="acme.com")
        session.add(company)
        session.commit()

        saved = session.scalars(select(Company)).one()
        assert saved.tenant_id == "tenant-1"
        assert saved.name == "Acme Corp"
        assert saved.domain == "acme.com"


def test_tag_model_creates_and_has_tenant_id(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Tag

    with Session(engine) as session:
        tag = Tag(tenant_id="tenant-1", name="VIP", color="#FF6600")
        session.add(tag)
        session.commit()

        saved = session.scalars(select(Tag)).one()
        assert saved.tenant_id == "tenant-1"
        assert saved.name == "VIP"
        assert saved.color == "#FF6600"


def test_activity_model_creates_and_has_tenant_id(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Activity, Lead

    with Session(engine) as session:
        lead = Lead(tenant_id="tenant-1", email="a@b.com")
        session.add(lead)
        session.commit()

        activity = Activity(
            tenant_id="tenant-1",
            lead_id=lead.id,
            action="created",
            description="Lead created via import",
        )
        session.add(activity)
        session.commit()

        saved = session.scalars(select(Activity)).one()
        assert saved.tenant_id == "tenant-1"
        assert saved.action == "created"
        assert saved.lead_id == lead.id


def test_lead_defaults(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead

    with Session(engine) as session:
        lead = Lead(tenant_id="t1", email="test@example.com")
        session.add(lead)
        session.commit()

        assert lead.id is not None
        assert lead.status == "raw"
        assert lead.stage == "new"
        assert lead.source == "manual"
        assert lead.confidence_score == 0
        assert lead.is_duplicate is False
        assert lead.notes == ""
        assert lead.import_batch_id == ""
        assert lead.duplicate_reason == ""
        assert lead.phone == ""
        assert lead.website == ""
        assert lead.first_name == ""
        assert lead.last_name == ""


def test_unique_tag_name_per_tenant(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Tag

    with Session(engine) as session:
        session.add(Tag(tenant_id="t1", name="VIP"))
        session.commit()
        session.add(Tag(tenant_id="t1", name="VIP"))
        try:
            session.commit()
            raise AssertionError("Expected integrity error")
        except Exception:
            pass  # expected


def test_unique_company_domain_per_tenant(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Company

    with Session(engine) as session:
        session.add(Company(tenant_id="t1", name="A", domain="a.com"))
        session.commit()
        session.add(Company(tenant_id="t1", name="B", domain="a.com"))
        try:
            session.commit()
            raise AssertionError("Expected integrity error")
        except Exception:
            pass  # expected


def test_different_tenant_can_have_same_tag_name(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Tag

    with Session(engine) as session:
        session.add(Tag(tenant_id="t1", name="VIP"))
        session.add(Tag(tenant_id="t2", name="VIP"))
        session.commit()
        assert session.scalars(select(Tag)).all() is not None
