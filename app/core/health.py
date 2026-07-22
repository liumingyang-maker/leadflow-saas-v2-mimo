from __future__ import annotations

from flask import Flask, jsonify
from sqlalchemy import text
from werkzeug.wrappers import Response

from app.extensions import get_engine


def register_health_routes(app: Flask) -> None:
    @app.get("/health/live")
    def health_live():
        return jsonify({"ok": True})

    @app.get("/health/ready")
    def health_ready():
        engine = get_engine(app)
        with engine.connect() as connection:
            connection.execute(text("select 1")).scalar_one()
        return jsonify({"ok": True, "checks": {"database": "ok"}})

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)
