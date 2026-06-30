"""Outreach service — send, tracking, suppression, templates."""

from __future__ import annotations

import hashlib
import hmac
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.leads.models import Activity
from app.modules.outreach.mailer import get_mailer
from app.modules.outreach.models import EmailTemplate, EmailTracking, OutreachMessage, Suppression


class OutreachError(ValueError):
    pass


def _session(app: Flask) -> Session:
    s = Session(get_engine(app))
    s.expire_on_commit = False
    return s


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def create_template(
    app: Flask, *, tenant_id: str, name: str, subject: str, body_text: str = "", body_html: str = ""
) -> EmailTemplate:
    with _session(app) as session:
        existing = session.scalar(
            select(EmailTemplate).where(
                EmailTemplate.tenant_id == tenant_id, EmailTemplate.name == name
            )
        )
        if existing:
            raise OutreachError("Template name already exists")
        t = EmailTemplate(
            tenant_id=tenant_id,
            name=name,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        session.add(t)
        session.commit()
        return t


def list_templates(app: Flask, *, tenant_id: str) -> list[EmailTemplate]:
    with _session(app) as session:
        return list(
            session.scalars(
                select(EmailTemplate)
                .where(EmailTemplate.tenant_id == tenant_id)
                .order_by(EmailTemplate.created_at.desc())
            )
        )


def get_template(app: Flask, *, template_id: str, tenant_id: str) -> EmailTemplate | None:
    with _session(app) as session:
        return session.scalar(
            select(EmailTemplate).where(
                EmailTemplate.id == template_id, EmailTemplate.tenant_id == tenant_id
            )
        )


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


def send_message(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    template_id: str = "",
) -> OutreachMessage:
    # Check suppression
    with _session(app) as session:
        suppressed = session.scalar(
            select(Suppression).where(
                Suppression.tenant_id == tenant_id, Suppression.email == to_email.strip().lower()
            )
        )
        if suppressed:
            msg = OutreachMessage(
                tenant_id=tenant_id,
                lead_id=lead_id,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                template_id=template_id,
                status="suppressed",
                provider="fake",
            )
            session.add(msg)
            _write_activity(
                session, tenant_id, lead_id, "email_suppressed", f"Email to {to_email} suppressed"
            )
            session.commit()
            return msg

    mailer = get_mailer()
    result = mailer.send(
        to_email=to_email, subject=subject, body_text=body_text, body_html=body_html
    )

    with _session(app) as session:
        if result.success:
            msg = OutreachMessage(
                tenant_id=tenant_id,
                lead_id=lead_id,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                template_id=template_id,
                status="sent",
                provider="fake",
                provider_message_id=result.provider_message_id,
                sent_at=datetime.now(UTC),
            )
            session.add(msg)
            session.flush()
            # Create tracking
            tracking = EmailTracking(
                tenant_id=tenant_id,
                lead_id=lead_id,
                message_id=msg.id,
                subject=subject,
                target_url="",
            )
            session.add(tracking)
            _write_activity(session, tenant_id, lead_id, "email_sent", f"Email sent to {to_email}")
            session.commit()
            return msg
        else:
            msg = OutreachMessage(
                tenant_id=tenant_id,
                lead_id=lead_id,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                template_id=template_id,
                status="failed",
                provider="fake",
                error_code=result.error_code,
                error_summary=result.error_summary,
            )
            session.add(msg)
            session.commit()
            return msg


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------


def get_tracking(app: Flask, *, tracking_id: str, tenant_id: str) -> EmailTracking | None:
    with _session(app) as session:
        return session.scalar(
            select(EmailTracking).where(
                EmailTracking.tracking_id == tracking_id, EmailTracking.tenant_id == tenant_id
            )
        )


def track_open(app: Flask, *, tracking_id: str) -> None:
    with _session(app) as session:
        tracking = session.get(EmailTracking, tracking_id)
        if tracking:
            now = datetime.now(UTC)
            tracking.open_count += 1
            if tracking.first_opened_at is None:
                tracking.first_opened_at = now
            tracking.last_opened_at = now
            session.commit()
            _write_activity(
                session, tracking.tenant_id, tracking.lead_id, "email_opened", "Email opened"
            )


def _signing_key(app: Flask) -> str:
    key = str(app.config.get("OUTREACH_SIGNING_KEY", ""))
    if not key:
        raise OutreachError("OUTREACH_SIGNING_KEY is not configured")
    return key


def sign_redirect(app: Flask, tracking_id: str, target_url: str, expires_at: int) -> str:
    msg = f"{tracking_id}:{target_url}:{expires_at}"
    return hmac.new(_signing_key(app).encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]


def verify_redirect(
    app: Flask, tracking_id: str, target_url: str, expires_at: int, sig: str
) -> bool:
    expected = sign_redirect(app, tracking_id, target_url, expires_at)
    return hmac.compare_digest(expected, sig)


def sign_unsubscribe_token(app: Flask, tracking_id: str, email: str) -> str:
    normal = email.strip().lower()
    sig = _unsubscribe_signature(app, tracking_id=tracking_id, email=normal)
    return urlsafe_b64encode(f"{tracking_id}:{normal}:{sig}".encode()).decode()


def verify_unsubscribe_token(app: Flask, token: str) -> tuple[str, str] | None:
    try:
        decoded = urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":", 2)
        if len(parts) != 3:
            return None
        tracking_id, email, sig = parts
        normal = email.strip().lower()
        expected = _unsubscribe_signature(app, tracking_id=tracking_id, email=normal)
        if not hmac.compare_digest(sig, expected):
            return None
        return tracking_id, normal
    except Exception:
        return None


def _unsubscribe_signature(app: Flask, *, tracking_id: str, email: str) -> str:
    msg = f"{tracking_id}:{email}"
    return hmac.new(_signing_key(app).encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]


def _is_safe_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    import socket
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
        ip = socket.gethostbyname(host)
        from ipaddress import ip_address, ip_network

        addr = ip_address(ip)
        for block in (
            "127.0.0.0/8",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "::1",
            "fc00::/7",
        ):
            if addr in ip_network(block):
                return False
        return True
    except Exception:
        return False


def track_click(app: Flask, *, tracking_id: str) -> bool:
    with _session(app) as session:
        tracking = session.get(EmailTracking, tracking_id)
        if tracking:
            now = datetime.now(UTC)
            tracking.click_count += 1
            if tracking.first_clicked_at is None:
                tracking.first_clicked_at = now
            tracking.last_clicked_at = now
            session.commit()
            _write_activity(
                session, tracking.tenant_id, tracking.lead_id, "email_clicked", "Email link clicked"
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Suppression / Unsubscribe
# ---------------------------------------------------------------------------


def unsubscribe(app: Flask, *, tenant_id: str, email: str) -> None:
    normal = email.strip().lower()
    with _session(app) as session:
        existing = session.scalar(
            select(Suppression).where(
                Suppression.tenant_id == tenant_id, Suppression.email == normal
            )
        )
        if existing is None:
            s = Suppression(tenant_id=tenant_id, email=normal, reason="unsubscribe")
            session.add(s)
            session.commit()


def is_suppressed(app: Flask, *, tenant_id: str, email: str) -> bool:
    with _session(app) as session:
        return (
            session.scalar(
                select(Suppression).where(
                    Suppression.tenant_id == tenant_id, Suppression.email == email.strip().lower()
                )
            )
            is not None
        )


# ---------------------------------------------------------------------------
# Activity helper
# ---------------------------------------------------------------------------


def _write_activity(
    session: Session, tenant_id: str, lead_id: str, action: str, description: str
) -> None:
    session.add(
        Activity(tenant_id=tenant_id, lead_id=lead_id, action=action, description=description[:500])
    )
