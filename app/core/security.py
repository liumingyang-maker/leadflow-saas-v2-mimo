from __future__ import annotations

from flask import Flask, Response, abort, request

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline';"
        " style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
        " font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    ),
}


def register_security_hooks(app: Flask) -> None:
    @app.before_request
    def enforce_host_allowlist() -> None:
        if not _deploy_security_enabled(app):
            return

        allowed_hosts = _allowed_hosts(app)
        if not allowed_hosts:
            abort(400)

        host = (request.host or "").lower()
        hostname = (request.host.split(":", 1)[0] if request.host else "").lower()
        if host not in allowed_hosts and hostname not in allowed_hosts:
            abort(400)

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if _deploy_security_enabled(app):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def _deploy_security_enabled(app: Flask) -> bool:
    return (
        not app.config.get("TESTING", False)
        and not app.config.get("DEBUG", False)
        and bool(app.config.get("SESSION_COOKIE_SECURE", False))
    )


def _allowed_hosts(app: Flask) -> set[str]:
    configured = str(app.config.get("ALLOWED_HOSTS", ""))
    return {host.strip().lower() for host in configured.split(",") if host.strip()}
