from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


def register_proxy_middleware(app: Flask) -> None:
    """Conditionally apply Werkzeug's ProxyFix middleware.

    Off by default.  When ``PROXY_FIX_HOPS`` is set to a positive integer
    the middleware trusts that many layers of reverse proxies and derives
    the real client IP from ``X-Forwarded-For`` / ``X-Forwarded-Proto``.
    """
    hops = _proxy_hops(app.config.get("PROXY_FIX_HOPS", 0))
    if hops > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)
    _register_ip_source(app)


def _register_ip_source(app: Flask) -> None:
    """Publish the resolved remote IP so other code can read it from
    ``request.remote_addr`` reliably."""

    @app.before_request
    def _resolve_client_ip() -> None:
        # When ProxyFix is active, request.remote_addr already reflects
        # the trusted X-Forwarded-For header.  When it is not, we use
        # the raw remote address.
        pass  # request.remote_addr is managed by Werkzeug/ProxyFix


def _proxy_hops(raw: object) -> int:
    try:
        hops = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("PROXY_FIX_HOPS must be an integer") from exc
    if hops < 0 or hops > 5:
        raise RuntimeError("PROXY_FIX_HOPS must be between 0 and 5")
    return hops
