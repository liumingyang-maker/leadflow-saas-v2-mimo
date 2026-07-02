from __future__ import annotations

from flask import Flask, redirect, render_template, request, session

from app.i18n import translate as t
from app.modules.accounts.guards import tenant_required
from app.modules.accounts.service import AccountError, complete_onboarding


def register_page_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        return redirect("/login")

    @app.get("/workbench")
    @tenant_required(app)
    def workbench():
        return render_template("app/workbench.html")

    @app.route("/onboarding", methods=["GET", "POST"])
    @tenant_required(app, allow_expired=True)
    def onboarding():
        tenant_id = session.get("tenant_id", "")
        if request.method == "POST":
            try:
                complete_onboarding(
                    app,
                    tenant_id=tenant_id,
                    industry=request.form.get("industry", ""),
                )
            except AccountError as error:
                return render_template("app/onboarding.html", error=t(error.message)), 400
            return redirect("/workbench")
        return render_template("app/onboarding.html", error="")

    @app.get("/upgrade")
    @tenant_required(app, allow_expired=True)
    def upgrade():
        return render_template("app/upgrade.html")
