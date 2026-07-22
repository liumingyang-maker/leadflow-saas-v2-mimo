"""Outreach routes — send, tracking, unsubscribe, templates."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from flask import Flask, Response, redirect, render_template, request, session
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.accounts.guards import tenant_required
from app.modules.leads.repository import LeadRepository
from app.modules.outreach.models import EmailTracking, OutreachMessage
from app.modules.outreach.service import (
    OutreachError,
    create_template,
    list_templates,
    send_message,
    track_click,
    track_open,
    unsubscribe,
    verify_redirect,
)
from app.modules.outreach.service import _is_safe_url as _safe_url


def register_outreach_routes(app: Flask) -> None:
    @app.get("/outreach")
    @tenant_required(app)
    def outreach_dashboard():
        tenant_id = session.get("tenant_id", "")
        templates = list_templates(app, tenant_id=tenant_id)
        engine = get_engine(app)
        with Session(engine) as db_session:
            sent = (
                db_session.scalar(
                    select(func.count(OutreachMessage.id)).where(
                        OutreachMessage.tenant_id == tenant_id, OutreachMessage.status == "sent"
                    )
                )
                or 0
            )
            failed = (
                db_session.scalar(
                    select(func.count(OutreachMessage.id)).where(
                        OutreachMessage.tenant_id == tenant_id, OutreachMessage.status == "failed"
                    )
                )
                or 0
            )
            suppressed = (
                db_session.scalar(
                    select(func.count(OutreachMessage.id)).where(
                        OutreachMessage.tenant_id == tenant_id,
                        OutreachMessage.status == "suppressed",
                    )
                )
                or 0
            )
            total_tracking = list(
                db_session.scalars(
                    select(EmailTracking).where(EmailTracking.tenant_id == tenant_id)
                )
            )
            opens = sum(t.open_count for t in total_tracking)
            clicks = sum(t.click_count for t in total_tracking)

        return render_template(
            "outreach/dashboard.html",
            templates=templates,
            sent=sent,
            failed=failed,
            suppressed=suppressed,
            opens=opens,
            clicks=clicks,
            total_sent=len(total_tracking),
        )

    @app.route("/outreach/templates", methods=["GET", "POST"])
    @tenant_required(app)
    def outreach_templates():
        tenant_id = session.get("tenant_id", "")
        if request.method == "POST":
            try:
                create_template(
                    app,
                    tenant_id=tenant_id,
                    name=request.form.get("name", ""),
                    subject=request.form.get("subject", ""),
                    body_text=request.form.get("body_text", ""),
                    body_html=request.form.get("body_html", ""),
                )
            except OutreachError as e:
                return render_template(
                    "outreach/templates.html",
                    templates=list_templates(app, tenant_id=tenant_id),
                    error=str(e),
                )
            return redirect("/outreach/templates")
        return render_template(
            "outreach/templates.html", templates=list_templates(app, tenant_id=tenant_id), error=""
        )

    @app.get("/leads/<lead_id>/outreach")
    @tenant_required(app)
    def lead_outreach(lead_id: str):
        tenant_id = session.get("tenant_id", "")
        engine = get_engine(app)
        with Session(engine) as db_session:
            lead = LeadRepository(db_session).get(lead_id, tenant_id=tenant_id)
            if lead is None:
                return redirect("/leads")
            templates = list_templates(app, tenant_id=tenant_id)
            messages = list(
                db_session.scalars(
                    select(OutreachMessage)
                    .where(
                        OutreachMessage.tenant_id == tenant_id, OutreachMessage.lead_id == lead_id
                    )
                    .order_by(OutreachMessage.created_at.desc())
                )
            )
        return render_template(
            "outreach/lead_send.html", lead=lead, templates=templates, messages=messages, error=""
        )

    @app.post("/leads/<lead_id>/outreach/send")
    @tenant_required(app)
    def lead_outreach_send(lead_id: str):
        tenant_id = session.get("tenant_id", "")
        to_email = request.form.get("to_email", "")
        subject = request.form.get("subject", "")
        body_text = request.form.get("body_text", "")
        body_html = request.form.get("body_html", "")
        template_id = request.form.get("template_id", "")
        engine = get_engine(app)
        with Session(engine) as db_session:
            lead = LeadRepository(db_session).get(lead_id, tenant_id=tenant_id)
        if lead is None:
            return redirect("/leads")
        try:
            send_message(
                app,
                tenant_id=tenant_id,
                lead_id=lead_id,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                template_id=template_id,
            )
        except OutreachError as e:
            templates = list_templates(app, tenant_id=tenant_id)
            with Session(engine) as db_session:
                messages = list(
                    db_session.scalars(
                        select(OutreachMessage)
                        .where(
                            OutreachMessage.tenant_id == tenant_id,
                            OutreachMessage.lead_id == lead_id,
                        )
                        .order_by(OutreachMessage.created_at.desc())
                    )
                )
            return render_template(
                "outreach/lead_send.html",
                lead=lead,
                templates=templates,
                messages=messages,
                error=str(e),
            )
        return redirect(f"/leads/{lead_id}/outreach")

    # Tracking pixel
    @app.get("/t/o/<tracking_id>.gif")
    def open_pixel(tracking_id: str):
        track_open(app, tracking_id=tracking_id)
        _1x1_gif = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
            b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
            b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        )
        return Response(
            _1x1_gif,
            mimetype="image/gif",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    # Click redirect
    @app.get("/t/c/<tracking_id>")
    def click_redirect(tracking_id: str):
        target = request.args.get("u", "")
        exp_str = request.args.get("exp", "0")
        sig = request.args.get("sig", "")
        try:
            expires_at = int(exp_str)
        except (ValueError, TypeError):
            return "Invalid link", 400
        if time.time() > expires_at:
            return "Link expired", 410
        if not verify_redirect(tracking_id, target, expires_at, sig):
            return "Invalid signature", 400
        if not _safe_url(target):
            return "Unsafe target", 400
        track_click(app, tracking_id=tracking_id)
        return redirect(target, 302)

    # Unsubscribe
    @app.route("/unsubscribe/<token>", methods=["GET", "POST"])
    def unsubscribe_route(token: str):
        # Simplified: token contains tracking_id:email:hmac
        try:
            from base64 import urlsafe_b64decode

            decoded = urlsafe_b64decode(token.encode()).decode()
            parts = decoded.split(":", 2)
            if len(parts) != 3:
                return "Invalid unsubscribe link", 400
            tracking_id, email, sig = parts
            expected = hmac.new(
                os.environ.get("UNSUBSCRIBE_SIGNING_KEY", "dev-unsub-key-not-for-prod").encode(),
                f"{tracking_id}:{email}".encode(),
                hashlib.sha256,
            ).hexdigest()[:32]
            if not hmac.compare_digest(sig, expected):
                return "Invalid unsubscribe link", 400
        except Exception:
            return "Invalid unsubscribe link", 400

        # Look up tracking without tenant scope since token is self-contained
        engine = get_engine(app)
        with Session(engine) as db_session:
            tracking = db_session.get(EmailTracking, tracking_id)
        if tracking is None:
            return "Unsubscribe link invalid", 400

        if request.method == "POST":
            unsubscribe(app, tenant_id=tracking.tenant_id, email=email)
            return render_template("outreach/unsubscribed.html")
        return render_template("outreach/unsubscribe_confirm.html", email=email, token=token)
