"""Inbound routes — management UI + API."""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session

from app.core.capabilities import Capability, is_enabled
from app.extensions import csrf
from app.modules.accounts.guards import tenant_required
from app.modules.inbound.service import (
    MAX_BODY_SIZE,
    InboundError,
    add_origin,
    check_idempotency,
    check_rate_limit,
    generate_token,
    get_token_info,
    inbound_fingerprint_key,
    list_origins,
    lookup_token,
    process_and_finalize,
    remove_origin,
)


def _inbound_response(
    payload: dict[str, Any] | str,
    status: int,
    origin: str | None,
    headers: dict[str, str] | None = None,
) -> tuple[Response, int]:
    """Unified response helper with CORS for all inbound API replies."""
    if isinstance(payload, str):
        resp = Response(payload, mimetype="application/json")
    else:
        resp = jsonify(payload)
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    if headers:
        for k, v in headers.items():
            resp.headers[k] = v
    return resp, status


def register_inbound_routes(app: Flask) -> None:
    # ------------------------------------------------------------------
    # Management UI
    # ------------------------------------------------------------------

    @app.get("/inbound")
    @tenant_required(app)
    def inbound_settings():
        tenant_id = session.get("tenant_id", "")
        token_info = get_token_info(app, tenant_id=tenant_id)
        origins = list_origins(app, tenant_id=tenant_id)
        # No token is generated on GET — user must click "Generate"
        return render_template(
            "inbound/settings.html", token_info=token_info, origins=origins, new_token=None
        )

    @app.post("/inbound/regenerate")
    @tenant_required(app)
    def inbound_regenerate():
        tenant_id = session.get("tenant_id", "")
        _, plaintext = generate_token(app, tenant_id=tenant_id)
        token_info = get_token_info(app, tenant_id=tenant_id)
        origins = list_origins(app, tenant_id=tenant_id)
        return render_template(
            "inbound/settings.html",
            token_info=token_info,
            origins=origins,
            new_token=plaintext,
            show_token=True,
        )

    @app.post("/inbound/origins")
    @tenant_required(app)
    def inbound_add_origin():
        tenant_id = session.get("tenant_id", "")
        origin = request.form.get("origin", "")
        try:
            add_origin(app, tenant_id=tenant_id, origin=origin)
        except InboundError as e:
            token_info = get_token_info(app, tenant_id=tenant_id)
            origins = list_origins(app, tenant_id=tenant_id)
            return render_template(
                "inbound/settings.html", token_info=token_info, origins=origins, error=str(e)
            )
        return redirect("/inbound")

    @app.post("/inbound/origins/<origin_id>/delete")
    @tenant_required(app)
    def inbound_delete_origin(origin_id: str):
        tenant_id = session.get("tenant_id", "")
        remove_origin(app, tenant_id=tenant_id, origin_id=origin_id)
        return redirect("/inbound")

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    @app.route("/api/inbound/<token>", methods=["OPTIONS", "POST"])
    @csrf.exempt
    def inbound_api(token: str):
        if not is_enabled(app, Capability.INBOUND_API):
            abort(404)
        if request.method == "OPTIONS":
            return _handle_preflight(app, token)

        return _handle_post(app, token)

    def _handle_preflight(app: Flask, token: str) -> Response:
        tok = lookup_token(app, plaintext=token)
        if tok is None:
            return jsonify({"error": "not_found"}), 404

        origin = request.headers.get("Origin", "")
        origins = list_origins(app, tenant_id=tok.tenant_id)

        if origin:
            allowed = any(o.origin == origin for o in origins)
            if not allowed:
                return jsonify({"error": "origin_not_allowed"}), 403
            resp = jsonify({"ok": True})
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Idempotency-Key"
            resp.headers["Vary"] = "Origin"
            return resp

        # Server-to-server — no origin required
        return jsonify({"ok": True})

    def _handle_post(app: Flask, token: str) -> Response:
        tok = lookup_token(app, plaintext=token)
        if tok is None:
            return _inbound_response({"error": "invalid_request"}, 404, None)

        tenant_id = tok.tenant_id
        digest = tok.token_digest
        ip = request.remote_addr or "unknown"
        origin = request.headers.get("Origin", "")

        if origin:
            origins = list_origins(app, tenant_id=tenant_id)
            if not any(o.origin == origin for o in origins):
                return _inbound_response({"error": "origin_not_allowed"}, 403, origin)

        # Rate limit
        if not check_rate_limit(app, scope=f"inbound:{digest[:16]}", bucket=ip):
            return _inbound_response({"error": "rate_limited"}, 429, origin)

        # Content type
        if not request.is_json:
            return _inbound_response({"error": "json_required"}, 415, origin)

        # Body size
        if request.content_length and request.content_length > MAX_BODY_SIZE:
            return _inbound_response({"error": "body_too_large"}, 413, origin)

        body: dict[str, Any] = request.get_json(silent=True) or {}

        # Idempotency
        idempotency_key = body.get("idempotency_key", "") or request.headers.get(
            "Idempotency-Key", ""
        )
        storage_key = idempotency_key or inbound_fingerprint_key(token_digest=digest, payload=body)
        idem_status, idem_response, claim_token = check_idempotency(
            app,
            tenant_id=tenant_id,
            token_digest=digest,
            idempotency_key=idempotency_key,
            payload=body,
        )
        if idem_status == "replayed":
            return _inbound_response(idem_response or "{}", 200, origin)
        if idem_status == "conflict":
            return _inbound_response({"error": "idempotency_key_conflict"}, 409, origin)
        if idem_status == "processing":
            return _inbound_response(
                {"error": "request_in_progress", "retry_after_seconds": 1},
                409,
                origin,
                headers={"Retry-After": "1"},
            )

        # Process + finalize in a single transaction (exactly-once)
        result, ownership_held = process_and_finalize(
            app,
            tenant_id=tenant_id,
            token_digest=digest,
            body=body,
            idempotency_key=idempotency_key,
            storage_key=storage_key,
            claim_token=claim_token,
        )

        if not ownership_held:
            return _inbound_response(
                {"error": "lease_lost", "retry": True},
                409,
                origin,
                headers={"Retry-After": "1"},
            )

        status = 200 if result.get("ok") else 400
        return _inbound_response(result, status, origin)
