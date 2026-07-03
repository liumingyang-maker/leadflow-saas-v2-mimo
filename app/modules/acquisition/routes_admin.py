from __future__ import annotations

from flask import Flask, redirect, render_template, request

from app.i18n import translate as t
from app.integrations.acquisition.search_api.base import SearchProviderError
from app.integrations.acquisition.search_api.brave import BraveSearchProvider
from app.integrations.acquisition.search_api.fake import FakeSearchProvider
from app.modules.accounts.admin_routes import admin_required
from app.modules.acquisition.service import (
    AcquisitionProviderError,
    acquisition_provider_secret,
    get_acquisition_settings,
    mark_acquisition_test_result,
    save_acquisition_settings,
)


def register_acquisition_admin_routes(app: Flask) -> None:
    @app.route("/admin/acquisition", methods=["GET", "POST"])
    @admin_required
    def admin_acquisition():
        message = ""
        error = ""
        if request.method == "POST":
            action = request.form.get("action", "save")
            if action == "test":
                ok, code = _test_provider(app)
                mark_acquisition_test_result(app, ok=ok, error_code=code)
                message = t("Acquisition provider test succeeded") if ok else ""
                error = "" if ok else f"{t('Acquisition provider test failed')}: {code}"
            else:
                try:
                    save_acquisition_settings(
                        app,
                        provider=request.form.get("provider", "disabled"),
                        enabled=bool(request.form.get("enabled")),
                        api_key=request.form.get("api_key", ""),
                        daily_spend_cap_cents=int(
                            request.form.get("daily_spend_cap_cents", "100") or 100
                        ),
                        query_limit_per_run=int(request.form.get("query_limit_per_run", "3") or 3),
                        result_limit_per_run=int(
                            request.form.get("result_limit_per_run", "10") or 10
                        ),
                        timeout_seconds=int(request.form.get("timeout_seconds", "10") or 10),
                    )
                except (AcquisitionProviderError, ValueError) as exc:
                    error = str(exc)
                else:
                    return redirect("/admin/acquisition")
        return render_template(
            "admin/acquisition.html",
            settings=get_acquisition_settings(app),
            message=message,
            error=error,
        )


def _test_provider(app: Flask) -> tuple[bool, str]:
    settings = get_acquisition_settings(app)
    if not settings.enabled or settings.provider == "disabled":
        return False, "provider_disabled"
    try:
        if settings.provider == "fake":
            provider = FakeSearchProvider()
        elif settings.provider == "brave":
            provider = BraveSearchProvider(
                api_key=acquisition_provider_secret(app),
                timeout_seconds=settings.timeout_seconds,
            )
        else:
            return False, "unsupported_provider"
        provider.search("test importer", limit=1)
    except SearchProviderError as exc:
        return False, exc.code
    return True, ""
