"""Audit routes — tenant-scoped and system-wide."""

from __future__ import annotations

from flask import Flask, render_template, session

from app.modules.accounts.admin_routes import admin_required
from app.modules.accounts.guards import tenant_required
from app.modules.audit.service import list_events


def register_audit_routes(app: Flask) -> None:
    @app.get("/audit")
    @tenant_required(app)
    def audit_list():
        tenant_id = session.get("tenant_id", "")
        events = list_events(app, tenant_id=tenant_id)
        return render_template("audit/list.html", events=events)

    @app.get("/admin/audit")
    @admin_required
    def admin_audit():
        events = list_events(app)
        return render_template("audit/admin_list.html", events=events)
