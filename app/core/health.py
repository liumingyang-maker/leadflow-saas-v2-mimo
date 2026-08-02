from __future__ import annotations

from flask import Flask, jsonify
from redis import Redis
from sqlalchemy import text
from werkzeug.wrappers import Response

from app.extensions import get_engine


def _database_ping(app: Flask) -> None:
    with get_engine(app).connect() as connection:
        connection.execute(text("select 1")).scalar_one()


def _redis_ping(app: Flask) -> None:
    client = Redis.from_url(
        str(app.config["REDIS_URL"]), socket_connect_timeout=2, socket_timeout=2
    )
    try:
        if client.ping() is not True:
            raise ConnectionError("redis ping did not return true")
    finally:
        client.close()


def register_health_routes(app: Flask) -> None:
    @app.get("/health/live")
    def health_live():
        return jsonify({"ok": True})

    @app.get("/health/ready")
    def health_ready():
        checks: dict[str, str] = {}
        for name, check in (("database", _database_ping), ("redis", _redis_ping)):
            try:
                check(app)
                checks[name] = "ok"
            except Exception:  # readiness must return a safe response for driver failures
                checks[name] = "error"
        if "error" in checks.values():
            return (
                jsonify(
                    {
                        "ok": False,
                        "checks": checks,
                        "error_code": "dependency_unavailable",
                    }
                ),
                503,
            )
        return jsonify({"ok": True, "checks": checks})

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)
