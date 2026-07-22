from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from flask import Flask, redirect, session

from app.modules.accounts.models import Tenant
from app.modules.accounts.repository import session_scope


def tenant_required(
    app: Flask, *, allow_expired: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            tenant_id = session.get("tenant_id")
            if not tenant_id:
                return redirect("/login")
            with session_scope(app) as db_session:
                tenant = db_session.get(Tenant, tenant_id)
                if tenant is None:
                    session.clear()
                    return redirect("/login")
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
