"""Tests for V2-03-002: Lead repositories and tenant isolation."""

from __future__ import annotations

import pytest
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


def test_lead_repository_tenant_isolation(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead_a = repo.add(
            Lead(email="a@tenant-a.com"),
            tenant_id="tenant-a",
        )
        lead_b = repo.add(
            Lead(email="b@tenant-b.com"),
            tenant_id="tenant-b",
        )
        session.commit()

        # Each tenant sees only their own leads
        assert repo.get(lead_a.id, tenant_id="tenant-a") is not None
        assert repo.get(lead_a.id, tenant_id="tenant-b") is None
        assert repo.get(lead_b.id, tenant_id="tenant-b") is not None
        assert repo.get(lead_b.id, tenant_id="tenant-a") is None

        assert len(repo.list(tenant_id="tenant-a")) == 1
        assert len(repo.list(tenant_id="tenant-b")) == 1


def test_lead_repository_crud(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(
            Lead(email="test@example.com", first_name="John"),
            tenant_id="t1",
        )
        session.commit()
        assert lead.id is not None

        # Read
        found = repo.get(lead.id, tenant_id="t1")
        assert found is not None
        assert found.email == "test@example.com"

        # Update
        repo.update(found, tenant_id="t1", first_name="Jane")
        session.commit()
        assert found.first_name == "Jane"

        # Delete
        repo.delete(found, tenant_id="t1")
        session.commit()
        assert repo.get(lead.id, tenant_id="t1") is None


def test_lead_repository_rejects_cross_tenant_update(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(Lead(email="a@a.com"), tenant_id="t1")
        session.commit()

        with pytest.raises(ValueError, match="tenant_id mismatch"):
            repo.update(lead, tenant_id="t2", first_name="Evil")


def test_lead_repository_rejects_cross_tenant_delete(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(Lead(email="a@a.com"), tenant_id="t1")
        session.commit()

        with pytest.raises(ValueError, match="tenant_id mismatch"):
            repo.delete(lead, tenant_id="t2")


def test_lead_repository_list_filters(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        repo.add(Lead(email="a@a.com", status="raw", stage="new"), tenant_id="t1")
        repo.add(Lead(email="b@b.com", status="accepted", stage="qualified"), tenant_id="t1")
        repo.add(
            Lead(email="c@c.com", status="rejected", stage="lost", is_duplicate=True),
            tenant_id="t1",
        )
        session.commit()

        assert len(repo.list(tenant_id="t1")) == 3
        assert len(repo.list(tenant_id="t1", status="raw")) == 1
        assert len(repo.list(tenant_id="t1", stage="qualified")) == 1
        assert len(repo.list(tenant_id="t1", is_duplicate=True)) == 1


def test_company_repository_tenant_isolation(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Company
    from app.modules.leads.repository import CompanyRepository

    with Session(engine) as session:
        repo = CompanyRepository(session)
        ca = repo.add(Company(name="A", domain="a.com"), tenant_id="t1")
        repo.add(Company(name="B", domain="b.com"), tenant_id="t2")
        session.commit()

        assert repo.get(ca.id, tenant_id="t1") is not None
        assert repo.get(ca.id, tenant_id="t2") is None
        assert repo.find_by_domain("a.com", tenant_id="t1") is not None
        assert repo.find_by_domain("a.com", tenant_id="t2") is None


def test_tag_repository_tenant_isolation(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Tag
    from app.modules.leads.repository import TagRepository

    with Session(engine) as session:
        repo = TagRepository(session)
        ta = repo.add(Tag(name="VIP"), tenant_id="t1")
        repo.add(Tag(name="Normal"), tenant_id="t2")
        session.commit()

        assert repo.get(ta.id, tenant_id="t1") is not None
        assert repo.get(ta.id, tenant_id="t2") is None
        assert len(repo.list(tenant_id="t1")) == 1


def test_activity_repository_tenant_isolation(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.models import Activity, Lead
    from app.modules.leads.repository import ActivityRepository, LeadRepository

    with Session(engine) as session:
        lead_repo = LeadRepository(session)
        activity_repo = ActivityRepository(session)
        lead = lead_repo.add(Lead(email="l@l.com"), tenant_id="t1")
        session.commit()

        act = activity_repo.add(
            Activity(lead_id=lead.id, action="created"),
            tenant_id="t1",
        )
        session.commit()

        # Can list activities for the lead
        activities = activity_repo.list_for_lead(lead.id, tenant_id="t1")
        assert len(activities) == 1
        assert activities[0].id == act.id

        # Wrong tenant sees empty list
        assert len(activity_repo.list_for_lead(lead.id, tenant_id="t2")) == 0


def test_empty_tenant_id_raises_error(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        with pytest.raises(ValueError, match="tenant_id is required"):
            repo.list(tenant_id="")
