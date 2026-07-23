"""Tenant-scoped repositories for Lead, Company, Tag, Activity."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.modules.leads.models import Activity, Company, Lead, Tag

# ---------------------------------------------------------------------------
# Tenant-scoped query helpers
# ---------------------------------------------------------------------------


def _tenant_scope(query: Select, model: type[Any], tenant_id: str) -> Select:
    return query.where(model.tenant_id == tenant_id)


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise ValueError("tenant_id is required")
    return clean


# ---------------------------------------------------------------------------
# LeadRepository
# ---------------------------------------------------------------------------


class LeadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, lead_id: str, *, tenant_id: str) -> Lead | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            _tenant_scope(
                select(Lead).where(Lead.id == lead_id),
                Lead,
                tenant_id,
            )
        )

    def list(
        self,
        *,
        tenant_id: str,
        status: str | None = None,
        stage: str | None = None,
        source: str | None = None,
        is_duplicate: bool | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Lead]:
        tenant_id = _require_tenant(tenant_id)
        query = _tenant_scope(select(Lead), Lead, tenant_id)

        if status:
            query = query.where(Lead.status == status)
        if stage:
            query = query.where(Lead.stage == stage)
        if source:
            query = query.where(Lead.source == source)
        if is_duplicate is not None:
            query = query.where(Lead.is_duplicate == is_duplicate)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    Lead.email.ilike(pattern),
                    Lead.first_name.ilike(pattern),
                    Lead.last_name.ilike(pattern),
                )
            )

        query = query.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(query))

    def add(self, lead: Lead, *, tenant_id: str) -> Lead:
        tenant_id = _require_tenant(tenant_id)
        if not lead.tenant_id:
            lead.tenant_id = tenant_id
        elif lead.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        self.session.add(lead)
        return lead

    def find_by_email(self, email: str, *, tenant_id: str) -> Lead | None:
        """Exact email lookup (normalized: stripped, lowercased). Tenant-scoped."""
        tenant_id = _require_tenant(tenant_id)
        normalized = (email or "").strip().lower()
        if not normalized:
            return None
        return self.session.scalar(
            _tenant_scope(
                select(Lead).where(Lead.email == normalized),
                Lead,
                tenant_id,
            )
        )

    def update(self, lead: Lead, *, tenant_id: str, **fields: Any) -> Lead:
        tenant_id = _require_tenant(tenant_id)
        if lead.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        for key, value in fields.items():
            if value is not None:
                setattr(lead, key, value)
        return lead

    def delete(self, lead: Lead, *, tenant_id: str) -> None:
        tenant_id = _require_tenant(tenant_id)
        if lead.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        self.session.delete(lead)

    def count(
        self,
        *,
        tenant_id: str,
        status: str | None = None,
        stage: str | None = None,
    ) -> int:
        tenant_id = _require_tenant(tenant_id)
        query = _tenant_scope(select(Lead), Lead, tenant_id)
        if status:
            query = query.where(Lead.status == status)
        if stage:
            query = query.where(Lead.stage == stage)
        return self.session.scalar(select(select(query).subquery().count()))


# ---------------------------------------------------------------------------
# CompanyRepository
# ---------------------------------------------------------------------------


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, company_id: str, *, tenant_id: str) -> Company | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            _tenant_scope(
                select(Company).where(Company.id == company_id),
                Company,
                tenant_id,
            )
        )

    def find_by_domain(self, domain: str, *, tenant_id: str) -> Company | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            _tenant_scope(
                select(Company).where(Company.domain == domain),
                Company,
                tenant_id,
            )
        )

    def list(self, *, tenant_id: str) -> Sequence[Company]:
        tenant_id = _require_tenant(tenant_id)
        query = _tenant_scope(select(Company), Company, tenant_id).order_by(Company.name)
        return list(self.session.scalars(query))

    def add(self, company: Company, *, tenant_id: str) -> Company:
        tenant_id = _require_tenant(tenant_id)
        if not company.tenant_id:
            company.tenant_id = tenant_id
        elif company.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        self.session.add(company)
        return company


# ---------------------------------------------------------------------------
# TagRepository
# ---------------------------------------------------------------------------


class TagRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, tag_id: str, *, tenant_id: str) -> Tag | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            _tenant_scope(select(Tag).where(Tag.id == tag_id), Tag, tenant_id)
        )

    def list(self, *, tenant_id: str) -> Sequence[Tag]:
        tenant_id = _require_tenant(tenant_id)
        query = _tenant_scope(select(Tag), Tag, tenant_id).order_by(Tag.name)
        return list(self.session.scalars(query))

    def add(self, tag: Tag, *, tenant_id: str) -> Tag:
        tenant_id = _require_tenant(tenant_id)
        if not tag.tenant_id:
            tag.tenant_id = tenant_id
        elif tag.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        self.session.add(tag)
        return tag


# ---------------------------------------------------------------------------
# ActivityRepository
# ---------------------------------------------------------------------------


class ActivityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_lead(self, lead_id: str, *, tenant_id: str) -> Sequence[Activity]:
        tenant_id = _require_tenant(tenant_id)
        query = _tenant_scope(
            select(Activity)
            .where(Activity.lead_id == lead_id)
            .order_by(Activity.created_at.desc()),
            Activity,
            tenant_id,
        )
        return list(self.session.scalars(query))

    def add(self, activity: Activity, *, tenant_id: str) -> Activity:
        tenant_id = _require_tenant(tenant_id)
        if not activity.tenant_id:
            activity.tenant_id = tenant_id
        elif activity.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        self.session.add(activity)
        return activity
