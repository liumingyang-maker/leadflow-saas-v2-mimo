"""Settings routes — tenant profile and environment status."""

from __future__ import annotations

import os

from flask import Flask, render_template, session
from sqlalchemy import select

from app.modules.accounts.admin_routes import admin_required
from app.modules.accounts.guards import tenant_required
from app.modules.accounts.models import Tenant
from app.modules.jobs.worker import _is_allowed_env as _fake_allowed


def register_settings_routes(app: Flask) -> None:
    @app.get("/settings")
    @tenant_required(app)
    def settings_index():
        tenant_id = session.get("tenant_id", "")
        from sqlalchemy.orm import Session

        from app.extensions import get_engine
        from app.modules.acquisition.models import ProviderStatus

        engine = get_engine(app)
        with Session(engine) as db_session:
            tenant = db_session.get(Tenant, tenant_id)
            provider = db_session.scalar(
                select(ProviderStatus).where(
                    ProviderStatus.tenant_id == tenant_id,
                    ProviderStatus.provider == "mimo",
                )
            )
            provider_status = (
                {
                    "status": provider.status,
                    "consecutive_failures": provider.consecutive_failures,
                    "error_code": provider.error_code,
                    "last_checked_at": provider.last_checked_at,
                    "last_success_at": provider.last_success_at,
                }
                if provider is not None
                else {
                    "status": "unknown",
                    "consecutive_failures": 0,
                    "error_code": "",
                    "last_checked_at": None,
                    "last_success_at": None,
                }
            )
        if tenant is None:
            return render_template(
                "settings/index.html",
                tenant=None,
                env_status=None,
                provider_status=None,
            )
        env_status = {
            "env": os.environ.get("APP_ENV", "development"),
            "csrf_enabled": bool(app.config.get("WTF_CSRF_ENABLED", True)),
            "proxy_enabled": int(app.config.get("PROXY_FIX_HOPS", 0)) > 0,
            "cookie_secure": bool(app.config.get("SESSION_COOKIE_SECURE", False)),
            "fake_mailer": _fake_allowed(),
            "fake_adapters": _fake_allowed(),
            "redis_configured": bool(os.environ.get("REDIS_URL", "")),
        }
        return render_template(
            "settings/index.html",
            tenant=tenant,
            env_status=env_status,
            provider_status=provider_status,
        )

    @app.get("/admin/system")
    @admin_required(app)
    def admin_system():
        import platform

        from app.extensions import engine_is_initialized

        info = {
            "python_version": platform.python_version(),
            "db_connected": engine_is_initialized(),
            "env": os.environ.get("APP_ENV", "development"),
            "redis_url_configured": bool(os.environ.get("REDIS_URL", "")),
        }
        return render_template("admin/system.html", info=info)
