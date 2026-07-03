"""Collection routes — create jobs, view status, list jobs."""

from __future__ import annotations

from flask import Flask, redirect, render_template, request, session

from app.i18n import get_locale
from app.i18n import translate as t
from app.integrations.acquisition.registry import acquisition_channels
from app.modules.accounts.guards import tenant_required
from app.modules.jobs.service import (
    JobServiceError,
    create_and_enqueue,
    get_job_status,
    list_jobs,
)
from app.modules.jobs.target_discovery import (
    add_candidate_to_crm,
    collection_target_context,
    filters_from_form,
    generate_basic_search_strategy_for_collection,
    generate_collection_target_plan,
    match_collection_target_candidates,
    parse_basic_search_results_for_collection,
    plan_json,
    raw_candidate_data,
)


def register_collection_routes(app: Flask) -> None:
    # ------------------------------------------------------------------
    # Collection workspace
    # ------------------------------------------------------------------

    @app.get("/collection")
    @tenant_required(app)
    def collection_workspace():
        return _render_collection_workspace(app)

    @app.post("/collection/target-plan")
    @tenant_required(app)
    def collection_target_plan():
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        result = generate_collection_target_plan(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            locale=get_locale(),
            form=request.form,
        )
        return _render_collection_workspace(
            app,
            target_error=_target_error_message(result.error_code) if not result.success else "",
            target_notice=t("Recommended buyer profile") if result.success else "",
        )

    @app.post("/collection/target-match")
    @tenant_required(app)
    def collection_target_match():
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        result = match_collection_target_candidates(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            locale=get_locale(),
            form=request.form,
        )
        return _render_collection_workspace(
            app,
            target_error=_target_error_message(result.error_code) if not result.success else "",
            target_notice=t("Example customers for testing") if result.success else "",
        )

    @app.post("/collection/channels/basic-search/strategy")
    @tenant_required(app)
    def collection_basic_search_strategy():
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        result = generate_basic_search_strategy_for_collection(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            locale=get_locale(),
            form=request.form,
        )
        return _render_collection_workspace(
            app,
            target_error=_target_error_message(result.error_code) if not result.success else "",
            target_notice=t("Search strategy generated") if result.success else "",
        )

    @app.post("/collection/channels/basic-search/parse-results")
    @tenant_required(app)
    def collection_basic_search_parse_results():
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        result = parse_basic_search_results_for_collection(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            locale=get_locale(),
            form=request.form,
        )
        return _render_collection_workspace(
            app,
            target_error=_target_error_message(result.error_code) if not result.success else "",
            target_notice=t("Search results parsed") if result.success else "",
        )

    @app.post("/collection/candidates/<candidate_id>/add-to-crm")
    @tenant_required(app)
    def add_collection_candidate_to_crm(candidate_id: str):
        tenant_id = session.get("tenant_id", "")
        user_id = session.get("user_id", "")
        result = add_candidate_to_crm(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            candidate_id=candidate_id,
        )
        if result.success:
            return redirect(f"/leads/{result.lead_id}")
        return _render_collection_workspace(
            app,
            target_error=_target_error_message(result.error_code),
        )

    # ------------------------------------------------------------------
    # Create Google Search job
    # ------------------------------------------------------------------

    @app.get("/collection/search")
    @tenant_required(app)
    def search_form():
        return render_template("collection/search_form.html", error="")

    @app.post("/collection/search")
    @tenant_required(app)
    def search_submit():
        tenant_id = session.get("tenant_id", "")
        query = request.form.get("query", "").strip()
        max_results = int(request.form.get("max_results", 20) or 20)

        if not query:
            return render_template("collection/search_form.html", error="Search query is required")

        payload = {"query": query, "max_results": max_results}
        try:
            job = create_and_enqueue(
                app, tenant_id=tenant_id, job_type="google_search", payload=payload
            )
        except (JobServiceError, ValueError) as exc:
            return render_template("collection/search_form.html", error=str(exc))

        return redirect(f"/collection/jobs/{job.id}")

    # ------------------------------------------------------------------
    # Create Google Maps job
    # ------------------------------------------------------------------

    @app.get("/collection/maps")
    @tenant_required(app)
    def maps_form():
        return render_template("collection/maps_form.html", error="")

    @app.post("/collection/maps")
    @tenant_required(app)
    def maps_submit():
        tenant_id = session.get("tenant_id", "")
        query = request.form.get("query", "").strip()
        location = request.form.get("location", "").strip()
        max_results = int(request.form.get("max_results", 20) or 20)

        if not query or not location:
            return render_template(
                "collection/maps_form.html", error="Both query and location are required"
            )

        payload = {"query": query, "location": location, "max_results": max_results}
        try:
            job = create_and_enqueue(
                app, tenant_id=tenant_id, job_type="google_maps", payload=payload
            )
        except (JobServiceError, ValueError) as exc:
            return render_template("collection/maps_form.html", error=str(exc))

        return redirect(f"/collection/jobs/{job.id}")

    # ------------------------------------------------------------------
    # Job status (HTMX polling target)
    # ------------------------------------------------------------------

    @app.get("/collection/jobs/<job_id>")
    @tenant_required(app)
    def job_detail(job_id: str):
        tenant_id = session.get("tenant_id", "")
        job = get_job_status(app, job_id=job_id, tenant_id=tenant_id)
        if job is None:
            return render_template("collection/job_not_found.html"), 404
        return render_template("collection/job_detail.html", job=job)

    @app.get("/collection/jobs/<job_id>/status")
    @tenant_required(app)
    def job_status_partial(job_id: str):
        tenant_id = session.get("tenant_id", "")
        job = get_job_status(app, job_id=job_id, tenant_id=tenant_id)
        if job is None:
            return "", 404
        return render_template("collection/_job_status.html", job=job)


def _render_collection_workspace(app: Flask, *, target_error: str = "", target_notice: str = ""):
    tenant_id = session.get("tenant_id", "")
    jobs = list_jobs(app, tenant_id=tenant_id, limit=50)
    target_context = collection_target_context(app, tenant_id=tenant_id)
    return render_template(
        "collection/workspace.html",
        jobs=jobs,
        target_context=target_context,
        target_plan=plan_json(target_context.latest_run),
        raw_candidate_data=raw_candidate_data,
        acquisition_channels=acquisition_channels(),
        target_filters=filters_from_form(request.form),
        target_error=target_error,
        target_notice=target_notice,
    )


def _target_error_message(error_code: str) -> str:
    if error_code == "missing_product_profile":
        return t("Please train your AI foreign trade operator first")
    if error_code in {"tenant_ai_disabled", "ai_disabled"}:
        return t("AI is not enabled for this workspace. Please contact the administrator.")
    if error_code == "duplicate_candidate":
        return t("Duplicate candidate detected")
    if error_code == "candidate_not_found":
        return t("Candidate not found")
    if error_code == "missing_search_results":
        return t("Paste search results")
    return t("System is busy, please try again later")
