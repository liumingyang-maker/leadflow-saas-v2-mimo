from __future__ import annotations

import re
import uuid

from flask import Flask, Response, g, request

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def register_request_id_hooks(app: Flask) -> None:
    @app.before_request
    def assign_request_id() -> None:
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        g.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex

    @app.after_request
    def attach_request_id(response: Response) -> Response:
        response.headers[REQUEST_ID_HEADER] = str(g.get("request_id", uuid.uuid4().hex))
        return response
