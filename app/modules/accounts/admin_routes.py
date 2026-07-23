from __future__ import annotations

from functools import wraps
from typing import Any

from flask import Flask, redirect, render_template, request, session

from app.modules.accounts.admin_service import (
    AdminAccountError,
    authenticate_admin,
    list_tenants_for_admin,
)
from app.modules.accounts.models import AdminUser
from app.modules.accounts.repository import session_scope


def register_admin_routes(app: Flask) -> None:
    @app.get("/admin/login")
    def admin_login_form():
        return render_template("admin/login.html", error="")

    @app.post("/admin/login")
    def admin_login_submit():
        try:
            identity = authenticate_admin(
                app,
                email=request.form.get("email", ""),
                password=request.form.get("password", ""),
            )
        except AdminAccountError as error:
            return render_template("admin/login.html", error=error.message), 200
        session.clear()
        session.permanent = True
        session["is_admin"] = True
        session["admin_id"] = identity.admin_id
        session["admin_email"] = identity.email
        session["admin_auth_version"] = identity.auth_version
        session["admin_must_change_password"] = identity.must_change_password
        return redirect("/admin")

    @app.get("/admin")
    @admin_required(app)
    def admin_console():
        tenants = list_tenants_for_admin(app)
        return render_template("admin/console.html", tenants=tenants)

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect("/admin/login")


def admin_required(app: Flask):
    """Decorator factory that verifies admin from database on each request."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            admin_id = session.get("admin_id")
            if not session.get("is_admin") or not admin_id:
                session.clear()
                return redirect("/admin/login")

            # Verify admin still exists and is active
            with session_scope(app) as db_session:
                admin = db_session.get(AdminUser, admin_id)
                if admin is None or admin.disabled_at is not None:
                    session.clear()
                    return redirect("/admin/login")

                # Verify auth_version (session revocation)
                session_version = session.get("admin_auth_version")
                if session_version is None or session_version != admin.auth_version:
                    session.clear()
                    return redirect("/admin/login")

                # Enforce must_change_password
                if admin.must_change_password:
                    session["admin_must_change_password"] = True

            return view(*args, **kwargs)

        return wrapped

    return decorator
