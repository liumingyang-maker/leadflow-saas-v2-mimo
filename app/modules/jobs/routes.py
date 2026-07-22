"""Collection routes — create jobs, view status, list jobs."""

from __future__ import annotations

from flask import Flask, redirect, render_template, request, session

from app.modules.accounts.guards import tenant_required
from app.modules.jobs.service import (
    JobServiceError,
    create_and_enqueue,
    get_job_status,
    list_jobs,
)


def register_collection_routes(app: Flask) -> None:
    # ------------------------------------------------------------------
    # Collection workspace
    # ------------------------------------------------------------------

    @app.get("/collection")
    @tenant_required(app)
    def collection_workspace():
        tenant_id = session.get("tenant_id", "")
        jobs = list_jobs(app, tenant_id=tenant_id, limit=50)
        return render_template("collection/workspace.html", jobs=jobs)

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
