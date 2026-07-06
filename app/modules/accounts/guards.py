from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from flask import Flask, redirect, session
from sqlalchemy import select

from app.modules.accounts.models import Tenant, TenantMembership, User
from app.modules.accounts.repository import session_scope


def tenant_required(
    app: Flask, *, allow_expired: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            redirect_target = ensure_tenant_context(app, allow_expired=allow_expired)
            if redirect_target:
                return redirect(redirect_target)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def ensure_tenant_context(app: Flask, *, allow_expired: bool = False) -> str | None:
    """Validate the session tenant and recover it from memberships when possible."""
    user_id = session.get("user_id")
    tenant_id = session.get("tenant_id")
    if not user_id:
        return _validate_legacy_tenant_session(
            app,
            tenant_id=tenant_id,
            allow_expired=allow_expired,
        )

    with session_scope(app) as db_session:
        memberships = db_session.scalars(
            select(TenantMembership)
            .join(Tenant)
            .where(TenantMembership.user_id == user_id)
            .order_by(TenantMembership.created_at, TenantMembership.id)
        ).all()
        if not memberships and tenant_id and db_session.get(User, user_id) is None:
            tenant = db_session.get(Tenant, tenant_id)
            if tenant is not None and tenant.status not in {"suspended", "deleted"}:
                if not allow_expired and tenant_is_expired(tenant):
                    return "/upgrade"
                return None
        membership = _select_membership(memberships, requested_tenant_id=tenant_id)
        if membership is None:
            app.logger.warning(
                "Tenant context recovery failed",
                extra={"user_id": user_id, "reason": "no_active_membership"},
            )
            session.clear()
            return "/login"

        tenant = membership.tenant
        session["tenant_id"] = tenant.id
        if not allow_expired and tenant_is_expired(tenant):
            return "/upgrade"
    return None


def _validate_legacy_tenant_session(
    app: Flask, *, tenant_id: str | None, allow_expired: bool
) -> str | None:
    if not tenant_id:
        return "/login"
    with session_scope(app) as db_session:
        tenant = db_session.get(Tenant, tenant_id)
        if tenant is None or tenant.status in {"suspended", "deleted"}:
            session.clear()
            return "/login"
        if not allow_expired and tenant_is_expired(tenant):
            return "/upgrade"
    return None


def _select_membership(
    memberships: list[TenantMembership], *, requested_tenant_id: str | None
) -> TenantMembership | None:
    usable_memberships = [
        membership
        for membership in memberships
        if membership.tenant.status not in {"suspended", "deleted"}
    ]
    if requested_tenant_id:
        for membership in usable_memberships:
            if membership.tenant_id == requested_tenant_id:
                return membership
    return usable_memberships[0] if usable_memberships else None


def tenant_is_expired(tenant: Tenant) -> bool:
    now = datetime.now(UTC)
    if tenant.status == "trial" and _past(tenant.trial_ends_at, now):
        return True
    if tenant.status == "active" and tenant.plan != "basic" and _past(tenant.plan_expires_at, now):
        return True
    return tenant.status == "expired"


def _past(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= now
