from __future__ import annotations

from flask import Flask, jsonify, session

from app.modules.accounts.guards import tenant_required
from app.modules.ai.service import OUTREACH_DRAFT_CREDITS, quota_summary


def register_ai_tenant_routes(app: Flask) -> None:
    @app.get("/ai/quota")
    @tenant_required(app)
    def tenant_ai_quota():
        tenant_id = session.get("tenant_id", "")
        summary = quota_summary(app, tenant_id=tenant_id)
        return jsonify(
            {
                "ok": True,
                "enabled": summary.enabled,
                "included": summary.included,
                "used": summary.used,
                "remaining": summary.remaining,
                "outreach_draft_credits": OUTREACH_DRAFT_CREDITS,
            }
        )
