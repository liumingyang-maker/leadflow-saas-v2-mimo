from __future__ import annotations

from flask import Flask, redirect, render_template, request, session

from app.i18n import get_locale
from app.i18n import translate as t
from app.modules.accounts.guards import tenant_required
from app.modules.onboarding.service import (
    confirm_profile,
    extract_and_save_profile,
    form_data_from_profile,
    get_product_profile,
    profile_field_text,
    save_draft_profile,
    website_needs_warning,
)


def register_onboarding_routes(app: Flask) -> None:
    @app.get("/onboarding/product-profile")
    @tenant_required(app)
    def onboarding_product_profile():
        tenant_id = session.get("tenant_id", "")
        profile = get_product_profile(app, tenant_id=tenant_id)
        form_data = form_data_from_profile(profile)
        return render_template(
            "onboarding/product_profile.html",
            profile=profile,
            raw_fields=form_data.raw_fields,
            extracted_profile=form_data.extracted_profile,
            profile_field_text=profile_field_text,
            website_warning=form_data.website_warning,
            error="",
            notice="",
            mode="onboarding",
        )

    @app.post("/onboarding/product-profile/extract")
    @tenant_required(app)
    def extract_onboarding_product_profile():
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        result = extract_and_save_profile(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            locale=get_locale(),
            form=request.form,
        )
        profile = get_product_profile(app, tenant_id=tenant_id)
        form_data = form_data_from_profile(profile)
        error = _extraction_error(result.error_code) if not result.success else ""
        return render_template(
            "onboarding/product_profile.html",
            profile=profile,
            raw_fields=form_data.raw_fields,
            extracted_profile=form_data.extracted_profile,
            profile_field_text=profile_field_text,
            website_warning=form_data.website_warning,
            error=error,
            notice="",
            mode="onboarding",
        )

    @app.post("/onboarding/product-profile/confirm")
    @tenant_required(app)
    def confirm_onboarding_product_profile():
        tenant_id = session.get("tenant_id", "")
        confirm_profile(app, tenant_id=tenant_id, form=request.form)
        return redirect("/workbench")

    @app.get("/settings/product-profile")
    @tenant_required(app)
    def settings_product_profile():
        tenant_id = session.get("tenant_id", "")
        profile = get_product_profile(app, tenant_id=tenant_id)
        form_data = form_data_from_profile(profile)
        return render_template(
            "settings/product_profile.html",
            profile=profile,
            raw_fields=form_data.raw_fields,
            extracted_profile=form_data.extracted_profile,
            profile_field_text=profile_field_text,
            website_warning=form_data.website_warning,
            error="",
            notice="",
            mode="settings",
        )

    @app.post("/settings/product-profile/update")
    @tenant_required(app)
    def update_settings_product_profile():
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        action = request.form.get("action", "save")
        notice = ""
        error = ""
        if action == "regenerate":
            result = extract_and_save_profile(
                app,
                tenant_id=tenant_id,
                user_id=user_id,
                locale=get_locale(),
                form=request.form,
            )
            error = _extraction_error(result.error_code) if not result.success else ""
        elif action == "confirm":
            confirm_profile(app, tenant_id=tenant_id, form=request.form)
            notice = t("Product profile saved")
        else:
            save_draft_profile(app, tenant_id=tenant_id, form=request.form)
            notice = t("Product profile saved")

        profile = get_product_profile(app, tenant_id=tenant_id)
        form_data = form_data_from_profile(profile)
        return render_template(
            "settings/product_profile.html",
            profile=profile,
            raw_fields=form_data.raw_fields,
            extracted_profile=form_data.extracted_profile,
            profile_field_text=profile_field_text,
            website_warning=website_needs_warning(form_data.raw_fields.get("raw_website_url", "")),
            error=error,
            notice=notice,
            mode="settings",
        )


def _extraction_error(error_code: str) -> str:
    if error_code in {"tenant_ai_disabled", "ai_disabled"}:
        return t("AI is not enabled for this workspace. Please contact the administrator.")
    return t("System is busy, please try again later")
