from __future__ import annotations

import os

from flask import Flask, jsonify
from redis import Redis
from sqlalchemy import text
from werkzeug.wrappers import Response

from app.extensions import get_engine


def register_health_routes(app: Flask) -> None:
    @app.get("/health/live")
    def health_live():
        return jsonify({"ok": True})

    @app.get("/health/ready")
    def health_ready():
        checks = {"database": "ok", "redis": "ok"}

        try:
            engine = get_engine(app)
            with engine.connect() as connection:
                connection.execute(text("select 1")).scalar_one()
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {exc.__class__.__name__}"

        if _redis_check_required(app):
            try:
                Redis.from_url(
                    str(app.config["REDIS_URL"]),
                    socket_connect_timeout=1,
                    socket_timeout=1,
                ).ping()
            except Exception as exc:  # noqa: BLE001
                checks["redis"] = f"error: {exc.__class__.__name__}"
        else:
            checks["redis"] = "skipped"

        ok = all(status == "ok" or status == "skipped" for status in checks.values())
        return jsonify({"ok": ok, "checks": checks}), 200 if ok else 503

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)


def _redis_check_required(app: Flask) -> bool:
    if app.config.get("TESTING") or app.config.get("DEBUG"):
        return "REDIS_URL" in os.environ
    return True
