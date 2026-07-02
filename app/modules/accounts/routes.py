from __future__ import annotations

import uuid

from flask import Flask, redirect, render_template, request, session

from app.core.abuse import rate_limit_clear, rate_limit_exceeded, rate_limit_hit
from app.i18n import translate as t
from app.modules.accounts.service import (
    AccountError,
    authenticate,
    register_account,
    request_password_reset,
    resend_verification_email,
    reset_password,
    verify_email,
)


def register_account_routes(app: Flask) -> None:
    @app.get("/register")
    def register_form():
        return render_template("auth/register.html", error="")

    @app.post("/register")
    def register_submit():
        email = request.form.get("email", "")
        if _request_rate_limited(app, "auth:register", [request.remote_addr or "unknown", email]):
            return render_template(
                "auth/register.html", error=t("Too many attempts. Try later.")
            ), 429
        try:
            register_account(
                app,
                email=email,
                password=request.form.get("password", ""),
                company_name=request.form.get("company_name", ""),
            )
        except AccountError as error:
            return render_template("auth/register.html", error=t(error.message)), 400
        return redirect("/login?registered=1")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("auth/login.html", error="")
        email = request.form.get("email", "")
        identifiers = [request.remote_addr or "unknown", email]
        if _login_blocked(app, "auth:login", identifiers):
            return render_template("auth/login.html", error=t("Too many attempts. Try later.")), 429
        try:
            identity = authenticate(
                app,
                email=email,
                password=request.form.get("password", ""),
            )
        except AccountError as error:
            _record_login_failure(app, "auth:login", identifiers)
            return render_template("auth/login.html", error=t(error.message)), 200

        rate_limit_clear(app, namespace="auth:login", identifiers=identifiers)
        session.clear()
        session.permanent = True
        session["tenant_id"] = identity.tenant_id
        session["tenant_email"] = identity.email
        session["user_id"] = identity.user_id
        session["auth_session_id"] = uuid.uuid4().hex
        return redirect("/workbench")

    @app.get("/verify-email/<token>")
    def verify_email_route(token: str):
        try:
            verify_email(app, token)
        except AccountError as error:
            return render_template("auth/verification_error.html", error=t(error.message)), 400
        return redirect("/login")

    @app.get("/resend-verification")
    def resend_verification_form():
        return render_template("auth/resend_verification.html", sent=False)

    @app.post("/resend-verification")
    def resend_verification_submit():
        email = request.form.get("email", "")
        if not _resend_verification_rate_limited(app, email):
            try:
                resend_verification_email(app, email=email)
            except AccountError:
                pass
        return render_template("auth/resend_verification.html", sent=True)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @app.get("/forgot-password")
    def forgot_password_form():
        return render_template("auth/forgot_password.html", sent=False)

    @app.post("/forgot-password")
    def forgot_password_submit():
        email = request.form.get("email", "")
        if _request_rate_limited(
            app, "auth:forgot-password", [request.remote_addr or "unknown", email]
        ):
            return render_template("auth/forgot_password.html", sent=True), 200
        try:
            request_password_reset(app, email=email)
        except AccountError:
            pass
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
                render_template("auth/reset_password.html", token=token, error=t(error.message)),
                400,
            )
        session.clear()
        return redirect("/login")


def _login_blocked(app: Flask, namespace: str, identifiers: list[str]) -> bool:
    return rate_limit_exceeded(
        app,
        namespace=namespace,
        identifiers=identifiers,
        limit=5,
    )


def _record_login_failure(app: Flask, namespace: str, identifiers: list[str]) -> None:
    rate_limit_hit(
        app,
        namespace=namespace,
        identifiers=identifiers,
        limit=5,
        window_seconds=15 * 60,
    )


def _request_rate_limited(app: Flask, namespace: str, identifiers: list[str]) -> bool:
    decision = rate_limit_hit(
        app,
        namespace=namespace,
        identifiers=identifiers,
        limit=5,
        window_seconds=15 * 60,
    )
    return not decision.allowed


def _resend_verification_rate_limited(app: Flask, email: str) -> bool:
    remote_addr = request.remote_addr or "unknown"
    clean_email = (email or "").strip().lower()[:320]
    checks = [
        rate_limit_hit(
            app,
            namespace="auth:resend-verify:email-cooldown",
            identifiers=[clean_email],
            limit=1,
            window_seconds=60,
        ),
        rate_limit_hit(
            app,
            namespace="auth:resend-verify:email-hour",
            identifiers=[clean_email],
            limit=5,
            window_seconds=60 * 60,
        ),
        rate_limit_hit(
            app,
            namespace="auth:resend-verify:ip-hour",
            identifiers=[remote_addr],
            limit=20,
            window_seconds=60 * 60,
        ),
    ]
    return any(not decision.allowed for decision in checks)
