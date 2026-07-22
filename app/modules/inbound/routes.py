"""Inbound routes — management UI + API."""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request, session

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
    process_inbound,
    remove_origin,
    store_idempotency,
)


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
            return jsonify({"error": "invalid_request"}), 404

        tenant_id = tok.tenant_id
        digest = tok.token_digest
        ip = request.remote_addr or "unknown"
        origin = request.headers.get("Origin", "")

        if origin:
            origins = list_origins(app, tenant_id=tenant_id)
            if not any(o.origin == origin for o in origins):
                return jsonify({"error": "origin_not_allowed"}), 403

        # Rate limit
        if not check_rate_limit(app, scope=f"inbound:{digest[:16]}", bucket=ip):
            return jsonify({"error": "rate_limited"}), 429

        # Content type
        if not request.is_json:
            return jsonify({"error": "json_required"}), 415

        # Body size
        if request.content_length and request.content_length > MAX_BODY_SIZE:
            return jsonify({"error": "body_too_large"}), 413

        body: dict[str, Any] = request.get_json(silent=True) or {}

        # Idempotency
        idempotency_key = body.get("idempotency_key", "") or request.headers.get(
            "Idempotency-Key", ""
        )
        storage_key = idempotency_key or inbound_fingerprint_key(token_digest=digest, payload=body)
        idem_status, idem_response = check_idempotency(
            app,
            tenant_id=tenant_id,
            token_digest=digest,
            idempotency_key=idempotency_key,
            payload=body,
        )
        if idem_status == "replayed":
            return Response(idem_response, mimetype="application/json"), 200
        if idem_status == "conflict":
            return jsonify({"error": "idempotency_key_conflict"}), 409
        if idem_status == "processing":
            return jsonify({"error": "request_in_progress"}), 409

        # Process
        result = process_inbound(
            app,
            tenant_id=tenant_id,
            token_digest=digest,
            body=body,
            idempotency_key=idempotency_key,
        )

        # Store idempotency
        store_idempotency(
            app,
            tenant_id=tenant_id,
            token_digest=digest,
            idempotency_key=storage_key,
            payload=body,
            status="completed" if result.get("ok") else "failed",
            response=result,
        )

        # CORS headers
        resp = jsonify(result)
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"

        status = 200 if result.get("ok") else 400
        return resp, status
