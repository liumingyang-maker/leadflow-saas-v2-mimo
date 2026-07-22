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
            tenant_id = session.get("tenant_id")
            user_id = session.get("user_id")
            # Both tenant_id and user_id are required
            if not tenant_id or not user_id:
                session.clear()
                return redirect("/login")

            with session_scope(app) as db_session:
                # Single join query: verify membership + user + tenant
                membership = db_session.scalar(
                    select(TenantMembership)
                    .join(User, TenantMembership.user_id == User.id)
                    .join(Tenant, TenantMembership.tenant_id == Tenant.id)
                    .where(
                        TenantMembership.tenant_id == tenant_id,
                        TenantMembership.user_id == user_id,
                    )
                )
                if membership is None:
                    session.clear()
                    return redirect("/login")

                user = membership.user
                tenant = membership.tenant

                # User must be active (not invited, not disabled)
                if not user.is_active or user.status != "active":
                    session.clear()
                    return redirect("/login")

                # Verify auth_version (session revocation)
                session_version = session.get("auth_version")
                if session_version is None or session_version != user.auth_version:
                    session.clear()
                    return redirect("/login")

                # Tenant must not be suspended
                if tenant.status == "suspended":
                    session.clear()
                    return redirect("/login")

                if not allow_expired and tenant_is_expired(tenant):
                    return redirect("/upgrade")

            return view(*args, **kwargs)

        return wrapped

    return decorator


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
