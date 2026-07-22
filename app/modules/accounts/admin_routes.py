from __future__ import annotations

from functools import wraps
from typing import Any

from flask import Flask, redirect, render_template, request, session

from app.modules.accounts.admin_service import (
    AdminAccountError,
    authenticate_admin,
    list_tenants_for_admin,
)


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
        session["admin_must_change_password"] = identity.must_change_password
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
        return view(*args, **kwargs)

    return wrapped
