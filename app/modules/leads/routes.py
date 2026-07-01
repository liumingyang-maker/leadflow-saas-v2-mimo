"""Lead and CRM routes — table, filters, detail, import, review."""

from __future__ import annotations

from flask import Flask, redirect, render_template, request, session

from app.modules.accounts.guards import tenant_required
from app.modules.leads.repository import (
    LeadRepository,
    TagRepository,
)
from app.modules.leads.safety import safe_external_url, safe_tag_color
from app.modules.leads.service import (
    LeadServiceError,
    add_note,
    add_tag,
    bulk_change_stage,
    bulk_delete,
    change_stage,
    confirm_import_batch,
    create_import_batch,
    get_timeline,
    remove_tag,
    review_lead,
)


def register_lead_routes(app: Flask) -> None:
    app.jinja_env.filters["external_url_href"] = safe_external_url
    app.jinja_env.filters["tag_border_color"] = safe_tag_color

    # ------------------------------------------------------------------
    # Lead list (CRM table)
    # ------------------------------------------------------------------

    @app.get("/leads")
    @tenant_required(app)
    def lead_list():
        tenant_id = session.get("tenant_id", "")
        status = request.args.get("status", "")
        stage = request.args.get("stage", "")
        search = request.args.get("search", "")

        from sqlalchemy.orm import Session

        from app.extensions import get_engine

        engine = get_engine(app)
        with Session(engine) as db_session:
            repo = LeadRepository(db_session)
            leads = repo.list(
                tenant_id=tenant_id,
                status=status or None,
                stage=stage or None,
                search=search or None,
            )
            tag_repo = TagRepository(db_session)
            tags = tag_repo.list(tenant_id=tenant_id)

        return render_template(
            "leads/list.html",
            leads=leads,
            tags=tags,
            current_status=status,
            current_stage=stage,
            current_search=search,
        )

    @app.get("/leads/<lead_id>")
    @tenant_required(app)
    def lead_detail(lead_id: str):
        tenant_id = session.get("tenant_id", "")

        from sqlalchemy.orm import Session

        from app.extensions import get_engine

        engine = get_engine(app)
        with Session(engine) as db_session:
            repo = LeadRepository(db_session)
            lead = repo.get(lead_id, tenant_id=tenant_id)
            if lead is None:
                return redirect("/leads")
            tag_repo = TagRepository(db_session)
            tags = tag_repo.list(tenant_id=tenant_id)
            timeline = get_timeline(app, tenant_id=tenant_id, lead_id=lead_id)

        return render_template(
            "leads/detail.html",
            lead=lead,
            tags=tags,
            timeline=timeline,
        )

    @app.get("/leads/<lead_id>/drawer")
    @tenant_required(app)
    def lead_drawer(lead_id: str):
        """HTMX partial — returns only the drawer content."""
        tenant_id = session.get("tenant_id", "")

        from sqlalchemy.orm import Session

        from app.extensions import get_engine

        engine = get_engine(app)
        with Session(engine) as db_session:
            repo = LeadRepository(db_session)
            lead = repo.get(lead_id, tenant_id=tenant_id)
            if lead is None:
                return '<div class="lf-alert" role="alert">Lead not found</div>', 404
            tag_repo = TagRepository(db_session)
            tags = tag_repo.list(tenant_id=tenant_id)
            timeline = get_timeline(app, tenant_id=tenant_id, lead_id=lead_id)

        return render_template(
            "leads/_drawer.html",
            lead=lead,
            tags=tags,
            timeline=timeline,
        )

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @app.get("/leads/import")
    @tenant_required(app)
    def import_form():
        return render_template("leads/import.html", preview=None, error="")

    @app.post("/leads/import")
    @tenant_required(app)
    def import_submit():
        tenant_id = session.get("tenant_id", "")
        action = request.form.get("action", "preview")

        try:
            if action == "confirm":
                batch_id = request.form.get("batch_id", "")
                if not batch_id:
                    return render_template(
                        "leads/import.html", preview=None, error="Missing batch ID"
                    )
                count = confirm_import_batch(app, tenant_id=tenant_id, batch_id=batch_id)
                return render_template(
                    "leads/import.html", preview=None, error="", success=f"Imported {count} leads"
                )
            else:
                file = request.files.get("file")
                if not file or not file.filename:
                    return render_template(
                        "leads/import.html", preview=None, error="No file selected"
                    )
                content = file.read()
                batch = create_import_batch(
                    app, tenant_id=tenant_id, filename=file.filename, content=content
                )
                return render_template("leads/import.html", batch=batch, preview=None, error="")
        except (LeadServiceError, ValueError) as exc:
            return render_template("leads/import.html", preview=None, error=str(exc))

    # ------------------------------------------------------------------
    # Review actions
    # ------------------------------------------------------------------

    @app.post("/leads/<lead_id>/review")
    @tenant_required(app)
    def lead_review(lead_id: str):
        tenant_id = session.get("tenant_id", "")
        decision = request.form.get("decision", "")
        try:
            review_lead(app, tenant_id=tenant_id, lead_id=lead_id, decision=decision)
        except LeadServiceError:
            pass
        return redirect(f"/leads/{lead_id}")

    @app.post("/leads/<lead_id>/stage")
    @tenant_required(app)
    def lead_change_stage(lead_id: str):
        tenant_id = session.get("tenant_id", "")
        stage = request.form.get("stage", "")
        try:
            change_stage(app, tenant_id=tenant_id, lead_id=lead_id, stage=stage)
        except LeadServiceError:
            pass
        return redirect(f"/leads/{lead_id}")

    @app.post("/leads/<lead_id>/note")
    @tenant_required(app)
    def lead_add_note(lead_id: str):
        tenant_id = session.get("tenant_id", "")
        note = request.form.get("note", "")
        try:
            add_note(app, tenant_id=tenant_id, lead_id=lead_id, note=note)
        except LeadServiceError:
            pass
        return redirect(f"/leads/{lead_id}")

    @app.post("/leads/<lead_id>/tag")
    @tenant_required(app)
    def lead_add_tag(lead_id: str):
        tenant_id = session.get("tenant_id", "")
        tag_name = request.form.get("tag_name", "")
        try:
            add_tag(app, tenant_id=tenant_id, lead_id=lead_id, tag_name=tag_name)
        except LeadServiceError:
            pass
        return redirect(f"/leads/{lead_id}")

    @app.post("/leads/<lead_id>/untag/<tag_id>")
    @tenant_required(app)
    def lead_remove_tag(lead_id: str, tag_id: str):
        tenant_id = session.get("tenant_id", "")
        try:
            remove_tag(app, tenant_id=tenant_id, lead_id=lead_id, tag_id=tag_id)
        except LeadServiceError:
            pass
        return redirect(f"/leads/{lead_id}")

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------

    @app.post("/leads/bulk/stage")
    @tenant_required(app)
    def leads_bulk_stage():
        tenant_id = session.get("tenant_id", "")
        lead_ids = request.form.getlist("lead_ids")
        stage = request.form.get("stage", "")
        try:
            bulk_change_stage(app, tenant_id=tenant_id, lead_ids=lead_ids, stage=stage)
        except LeadServiceError:
            pass
        return redirect("/leads")

    @app.post("/leads/bulk/delete")
    @tenant_required(app)
    def leads_bulk_delete():
        tenant_id = session.get("tenant_id", "")
        lead_ids = request.form.getlist("lead_ids")
        try:
            bulk_delete(app, tenant_id=tenant_id, lead_ids=lead_ids)
        except LeadServiceError:
            pass
        return redirect("/leads")
