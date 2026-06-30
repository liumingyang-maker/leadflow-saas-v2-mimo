from __future__ import annotations

from flask import Flask, render_template


def register_design_system_routes(app: Flask) -> None:
    @app.get("/_design-system")
    def design_system_preview():
        return render_template("design_system/preview.html")
