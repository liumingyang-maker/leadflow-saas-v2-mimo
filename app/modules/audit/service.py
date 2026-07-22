"""Audit service — write and query audit events."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from flask import Flask, request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.audit.models import AuditEvent


def _session(app: Flask) -> Session:
    s = Session(get_engine(app))
    s.expire_on_commit = False
    return s


def _hash(val: str, length: int = 16) -> str:
    return hashlib.sha256((val or "").encode()).hexdigest()[:length]


def record_event(
    app: Flask,
    *,
    tenant_id: str = "",
    actor_user_id: str = "",
    actor_admin_id: str = "",
    actor_type: str = "user",
    action: str,
    target_type: str = "",
    target_id: str = "",
    safe_summary: str = "",
) -> AuditEvent:
    ip = request.remote_addr or "" if hasattr(request, "remote_addr") else ""
    ua = request.headers.get("User-Agent", "") if hasattr(request, "headers") else ""
    with _session(app) as session:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_admin_id=actor_admin_id,
            actor_type=actor_type,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_hash=_hash(ip),
            user_agent_hash=_hash(ua),
            safe_summary=safe_summary[:500],
        )
        session.add(event)
        session.commit()
        return event


def list_events(app: Flask, *, tenant_id: str = "", limit: int = 100) -> Sequence[AuditEvent]:
    with _session(app) as session:
        q = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        if tenant_id:
            q = q.where(AuditEvent.tenant_id == tenant_id)
        return list(session.scalars(q))
