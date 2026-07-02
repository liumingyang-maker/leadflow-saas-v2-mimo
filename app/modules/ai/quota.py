from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import Tenant
from app.modules.ai.ledger import used_credits_for_period
from app.modules.ai.models import TenantAIQuota

PLAN_DEFAULT_CREDITS = {
    "basic": 1000,
    "pro": 5000,
    "ultra": 5000,
    "trial": 100,
}


@dataclass(frozen=True)
class QuotaSummary:
    enabled: bool
    included: int
    used: int
    remaining: int
    period_start: datetime
    period_end: datetime


def current_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    value = now or datetime.now(UTC)
    start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def ensure_quota(session: Session, *, tenant_id: str) -> TenantAIQuota:
    quota = session.scalar(select(TenantAIQuota).where(TenantAIQuota.tenant_id == tenant_id))
    start, end = current_period()
    if quota is not None:
        if _as_utc(quota.current_period_end) <= datetime.now(UTC):
            quota.current_period_start = start
            quota.current_period_end = end
        return quota

    tenant = session.get(Tenant, tenant_id)
    plan = "trial" if tenant is not None and tenant.status == "trial" else "basic"
    if tenant is not None and tenant.status != "trial":
        plan = tenant.plan
    quota = TenantAIQuota(
        tenant_id=tenant_id,
        enabled=True,
        plan_name=plan,
        monthly_included_credits=PLAN_DEFAULT_CREDITS.get(plan, 100),
        current_period_start=start,
        current_period_end=end,
    )
    session.add(quota)
    session.flush()
    return quota


def summarize_quota(session: Session, *, tenant_id: str) -> QuotaSummary:
    quota = ensure_quota(session, tenant_id=tenant_id)
    used = used_credits_for_period(
        session,
        tenant_id=tenant_id,
        period_start=_as_utc(quota.current_period_start),
        period_end=_as_utc(quota.current_period_end),
    )
    remaining = max(0, quota.monthly_included_credits - used)
    return QuotaSummary(
        enabled=quota.enabled,
        included=quota.monthly_included_credits,
        used=used,
        remaining=remaining,
        period_start=quota.current_period_start,
        period_end=quota.current_period_end,
    )


def has_credits(session: Session, *, tenant_id: str, required: int) -> bool:
    summary = summarize_quota(session, tenant_id=tenant_id)
    return summary.enabled and summary.remaining >= required


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
