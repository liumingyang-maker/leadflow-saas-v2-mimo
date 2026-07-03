from __future__ import annotations

import json

from flask import Flask

from app.config import resolve_config
from app.core.design_system import register_design_system_routes
from app.core.errors import register_error_handlers
from app.core.health import register_health_routes
from app.core.pages import register_page_routes
from app.core.proxy import register_proxy_middleware
from app.core.request_id import register_request_id_hooks
from app.core.security import register_security_hooks
from app.extensions import init_extensions
from app.i18n import register_i18n
from app.modules.accounts.admin_routes import register_admin_routes
from app.modules.accounts.routes import register_account_routes
from app.modules.admin.routes import register_admin_dashboard_routes
from app.modules.ai.routes_admin import register_ai_admin_routes
from app.modules.ai.routes_tenant import register_ai_tenant_routes
from app.modules.audit.routes import register_audit_routes
from app.modules.inbound.routes import register_inbound_routes
from app.modules.jobs.routes import register_collection_routes
from app.modules.leads.routes import register_lead_routes
from app.modules.onboarding.routes import register_onboarding_routes
from app.modules.outreach.routes import register_outreach_routes
from app.modules.settings.routes import register_settings_routes


def create_app(config_name: str | None = None) -> Flask:
    flask_app = Flask(__name__)
    flask_app.config.from_object(resolve_config(config_name))
    init_extensions(flask_app)
    register_i18n(flask_app)
    register_proxy_middleware(flask_app)
    register_request_id_hooks(flask_app)
    register_security_hooks(flask_app)
    register_error_handlers(flask_app)
    register_health_routes(flask_app)
    register_design_system_routes(flask_app)
    register_account_routes(flask_app)
    register_admin_dashboard_routes(flask_app)
    register_admin_routes(flask_app)
    register_ai_admin_routes(flask_app)
    register_ai_tenant_routes(flask_app)
    register_audit_routes(flask_app)
    register_collection_routes(flask_app)
    register_inbound_routes(flask_app)
    register_lead_routes(flask_app)
    register_onboarding_routes(flask_app)
    register_outreach_routes(flask_app)
    register_page_routes(flask_app)
    register_settings_routes(flask_app)

    flask_app.jinja_env.filters["from_json"] = json.loads

    return flask_app
