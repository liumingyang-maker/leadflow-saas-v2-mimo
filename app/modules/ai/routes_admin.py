from __future__ import annotations

from flask import Flask, redirect, render_template, request

from app.i18n import translate as t
from app.modules.accounts.admin_routes import admin_required
from app.modules.ai.service import (
    AIServiceError,
    admin_ai_overview,
    save_provider_settings,
    test_provider_connection,
)


def register_ai_admin_routes(app: Flask) -> None:
    @app.route("/admin/ai", methods=["GET", "POST"])
    @admin_required
    def admin_ai():
        message = ""
        error = ""
        if request.method == "POST":
            action = request.form.get("action", "save")
            if action == "test":
                ok, reason = test_provider_connection(app)
                message = t("AI provider connection succeeded") if ok else ""
                error = "" if ok else t("AI provider connection failed")
                if reason and not ok:
                    error = f"{error}: {reason}"
            else:
                try:
                    save_provider_settings(
                        app,
                        provider=request.form.get("provider", "disabled"),
                        enabled=bool(request.form.get("enabled")),
                        base_url=request.form.get("base_url", ""),
                        model=request.form.get("model", ""),
                        api_key=request.form.get("api_key", ""),
                        timeout_seconds=int(request.form.get("timeout_seconds", "25") or 25),
                        max_output_tokens=int(request.form.get("max_output_tokens", "800") or 800),
                    )
                except (AIServiceError, ValueError) as exc:
                    error = str(exc)
                else:
                    return redirect("/admin/ai")
        overview = admin_ai_overview(app)
        return render_template(
            "admin/ai.html",
            settings=overview["settings"],
            quotas=overview["quotas"],
            usage=overview["usage"],
            message=message,
            error=error,
        )
