"""Entrypoint for the resolving HTTPS-only Browser egress proxy."""

from __future__ import annotations

import asyncio
import os

from app.integrations.browser.egress_proxy import serve


def main() -> None:
    host = os.environ.get("BROWSER_EGRESS_HOST", "0.0.0.0")
    port = int(os.environ.get("BROWSER_EGRESS_PORT", "8080"))
    asyncio.run(serve(host=host, port=port))


if __name__ == "__main__":
    main()
