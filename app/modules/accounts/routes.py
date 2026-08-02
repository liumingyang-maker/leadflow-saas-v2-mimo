from __future__ import annotations

import uuid

from flask import Flask, abort, redirect, render_template, request, session

from app.core.capabilities import Capability, is_enabled
from app.modules.accounts.service import (
    AccountError,
    authenticate,
    register_account,
    request_password_reset,
    reset_password,
    verify_email,
)


def register_account_routes(app: Flask) -> None:
    @app.get("/register")
    def register_form():
        if not is_enabled(app, Capability.PUBLIC_REGISTRATION):
            abort(404)
        return render_template("auth/register.html", error="")

    @app.post("/register")
    def register_submit():
        if not is_enabled(app, Capability.PUBLIC_REGISTRATION):
            abort(404)
        try:
            verification_token = register_account(
                app,
                email=request.form.get("email", ""),
                password=request.form.get("password", ""),
                company_name=request.form.get("company_name", ""),
            )
        except AccountError as error:
            return render_template("auth/register.html", error=error.message), 400
        if app.config.get("LOCAL_EMAIL_VERIFICATION", False):
            session["local_verification_token"] = verification_token.token
        return redirect("/login?registered=1")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template(
                "auth/login.html",
                error="",
                local_verification_available=_local_verification_available(app),
            )
        try:
            identity = authenticate(
                app,
                email=request.form.get("email", ""),
                password=request.form.get("password", ""),
            )
        except AccountError as error:
            return (
                render_template(
                    "auth/login.html",
                    error=error.message,
                    local_verification_available=_local_verification_available(app),
                ),
                200,
            )

        session.clear()
        session.permanent = True
        session["tenant_id"] = identity.tenant_id
        session["tenant_email"] = identity.email
        session["user_id"] = identity.user_id
        session["auth_session_id"] = uuid.uuid4().hex
        session["auth_version"] = identity.auth_version
        return redirect("/workbench")

    @app.get("/verify-email/<token>")
    def verify_email_route(token: str):
        try:
            verify_email(app, token)
        except AccountError as error:
            return render_template("auth/verification_error.html", error=error.message), 400
        return redirect("/login")

    @app.post("/verify-email/local")
    def verify_email_local_route():
        if not app.config.get("LOCAL_EMAIL_VERIFICATION", False):
            abort(404)
        token = session.get("local_verification_token", "")
        if not token:
            abort(404)
        try:
            verify_email(app, token)
        except AccountError as error:
            return render_template("auth/verification_error.html", error=error.message), 400
        session.pop("local_verification_token", None)
        return redirect("/login?verified=1")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @app.get("/forgot-password")
    def forgot_password_form():
        return render_template("auth/forgot_password.html", sent=False)

    @app.post("/forgot-password")
    def forgot_password_submit():
        request_password_reset(app, email=request.form.get("email", ""))
        return render_template("auth/forgot_password.html", sent=True)

    @app.get("/reset-password/<token>")
    def reset_password_form(token: str):
        return render_template("auth/reset_password.html", token=token, error="")

    @app.post("/reset-password/<token>")
    def reset_password_submit(token: str):
        try:
            reset_password(app, token=token, password=request.form.get("password", ""))
        except AccountError as error:
            return (
                render_template("auth/reset_password.html", token=token, error=error.message),
                400,
            )
        session.clear()
        return redirect("/login")


def _local_verification_available(app: Flask) -> bool:
    return bool(
        app.config.get("LOCAL_EMAIL_VERIFICATION", False)
        and session.get("local_verification_token")
    )
