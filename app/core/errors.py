from __future__ import annotations

from http import HTTPStatus

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "request_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        code = error.code or 500
        error_code = HTTP_ERROR_CODES.get(code, "http_error")
        if _wants_json():
            return jsonify({"ok": False, "error": error_code}), code
        template = f"errors/{code}.html"
        if code not in {403, 404, 500}:
            template = "errors/500.html"
        return render_template(template), code

    @app.errorhandler(Exception)
    def handle_unexpected_exception(_error: Exception):
        if not _wants_json():
            return (
                render_template("errors/500.html"),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return jsonify({"ok": False, "error": "internal_error"}), HTTPStatus.INTERNAL_SERVER_ERROR


def _wants_json() -> bool:
    return (
        request.accept_mimetypes.best == "application/json"
        or request.path.startswith("/api/")
        or request.is_json
    )
