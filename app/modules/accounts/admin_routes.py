from __future__ import annotations

from functools import wraps
from typing import Any

from flask import Flask, redirect, render_template, request, session

from app.core.abuse import rate_limit_clear, rate_limit_exceeded, rate_limit_hit
from app.modules.accounts.admin_service import (
    AdminAccountError,
    authenticate_admin,
    change_admin_password,
    list_tenants_for_admin,
)


def register_admin_routes(app: Flask) -> None:
    @app.get("/admin/login")
    def admin_login_form():
        return render_template("admin/login.html", error="")

    @app.post("/admin/login")
    def admin_login_submit():
        email = request.form.get("email", "")
        identifiers = [request.remote_addr or "unknown", email]
        if _admin_login_blocked(app, identifiers):
            return render_template("admin/login.html", error="Too many attempts. Try later."), 429
        try:
            identity = authenticate_admin(
                app,
                email=email,
                password=request.form.get("password", ""),
            )
        except AdminAccountError as error:
            _record_admin_login_failure(app, identifiers)
            return render_template("admin/login.html", error=error.message), 200
        rate_limit_clear(app, namespace="auth:admin-login", identifiers=identifiers)
        session.clear()
        session.permanent = True
        session["is_admin"] = True
        session["admin_id"] = identity.admin_id
        session["admin_email"] = identity.email
        session["admin_must_change_password"] = identity.must_change_password
        return redirect("/admin")

    @app.get("/admin/change-password")
    def admin_change_password_form():
        if not session.get("is_admin"):
            return redirect("/admin/login")
        return render_template("admin/change_password.html", error="")

    @app.post("/admin/change-password")
    def admin_change_password_submit():
        if not session.get("is_admin"):
            return redirect("/admin/login")
        try:
            change_admin_password(
                app,
                admin_id=str(session.get("admin_id", "")),
                password=request.form.get("password", ""),
            )
        except AdminAccountError as error:
            return render_template("admin/change_password.html", error=error.message), 400
        session["admin_must_change_password"] = False
        return redirect("/admin")

    @app.get("/admin")
    @admin_required
    def admin_console():
        tenants = list_tenants_for_admin(app)
        return render_template("admin/console.html", tenants=tenants)

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect("/admin/login")


def admin_required(view):
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not session.get("is_admin"):
            return redirect("/admin/login")
        if session.get("admin_must_change_password"):
            return redirect("/admin/change-password")
        return view(*args, **kwargs)

    return wrapped


def _admin_login_blocked(app: Flask, identifiers: list[str]) -> bool:
    return rate_limit_exceeded(
        app,
        namespace="auth:admin-login",
        identifiers=identifiers,
        limit=5,
    )


def _record_admin_login_failure(app: Flask, identifiers: list[str]) -> None:
    rate_limit_hit(
        app,
        namespace="auth:admin-login",
        identifiers=identifiers,
        limit=5,
        window_seconds=15 * 60,
    )
