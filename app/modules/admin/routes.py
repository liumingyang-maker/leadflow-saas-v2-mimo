"""Admin routes — dashboard, tenant list, system admin only."""

from __future__ import annotations

from flask import Flask, render_template
from sqlalchemy import select

from app.extensions import get_engine
from app.modules.accounts.admin_routes import admin_required
from app.modules.accounts.models import Tenant


def register_admin_dashboard_routes(app: Flask) -> None:
    @app.get("/admin/dashboard")
    @admin_required(app)
    def admin_dashboard():
        """Admin overview with tenant stats."""
        engine = get_engine(app)
        from sqlalchemy.orm import Session

        with Session(engine) as db_session:
            tenants = list(
                db_session.scalars(select(Tenant).order_by(Tenant.created_at.desc()).limit(100))
            )
            tenant_count = len(tenants)
            active_count = sum(1 for t in tenants if t.status == "active")
            suspended_count = sum(1 for t in tenants if t.status == "suspended")
        return render_template(
            "admin/dashboard.html",
            tenants=tenants,
            tenant_count=tenant_count,
            active_count=active_count,
            suspended_count=suspended_count,
        )
