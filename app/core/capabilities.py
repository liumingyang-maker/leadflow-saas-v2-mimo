"""Deployment profile and capability service.

Centralizes Internal/Commercial mode decisions. All feature gates
must query this service — never scatter mode checks across routes.

COMMERCIALIZATION_HOOK:
Future external-customer behavior must be implemented behind CapabilityService.
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Literal, TypeAlias

from flask import Flask

DeploymentMode: TypeAlias = Literal["internal", "commercial"]

VALID_MODES = {"internal", "commercial"}


class Capability(StrEnum):
    PUBLIC_REGISTRATION = "public_registration"
    BILLING = "billing"
    PAYMENT_WEBHOOKS = "payment_webhooks"
    INBOUND_API = "inbound_api"
    OUTREACH_SEND = "outreach_send"
    MULTI_TENANT_SELF_SERVICE = "multi_tenant_self_service"
    ADMIN_CONSOLE = "admin_console"
    INVITE_ONLY = "invite_only"


# Internal Mode defaults: what is enabled/disabled for team-internal use
_INTERNAL_DEFAULTS: dict[Capability, bool] = {
    Capability.PUBLIC_REGISTRATION: False,
    Capability.BILLING: False,
    Capability.PAYMENT_WEBHOOKS: False,
    Capability.INBOUND_API: False,
    Capability.OUTREACH_SEND: True,
    Capability.MULTI_TENANT_SELF_SERVICE: False,
    Capability.ADMIN_CONSOLE: True,
    Capability.INVITE_ONLY: True,
}

# Commercial Mode defaults (future use)
_COMMERCIAL_DEFAULTS: dict[Capability, bool] = {
    Capability.PUBLIC_REGISTRATION: True,
    Capability.BILLING: True,
    Capability.PAYMENT_WEBHOOKS: True,
    Capability.INBOUND_API: True,
    Capability.OUTREACH_SEND: True,
    Capability.MULTI_TENANT_SELF_SERVICE: True,
    Capability.ADMIN_CONSOLE: True,
    Capability.INVITE_ONLY: False,
}

# Environment variable mapping for explicit overrides
_ENV_MAP: dict[Capability, str] = {
    Capability.PUBLIC_REGISTRATION: "ALLOW_PUBLIC_REGISTRATION",
    Capability.BILLING: "BILLING_ENABLED",
    Capability.PAYMENT_WEBHOOKS: "PAYMENT_WEBHOOKS_ENABLED",
    Capability.INBOUND_API: "INBOUND_API_ENABLED",
    Capability.OUTREACH_SEND: "OUTREACH_SEND_ENABLED",
    Capability.MULTI_TENANT_SELF_SERVICE: "MULTI_TENANT_SELF_SERVICE",
    Capability.ADMIN_CONSOLE: "ADMIN_CONSOLE_ENABLED",
    Capability.INVITE_ONLY: "INVITE_ONLY",
}


def _parse_bool(value: str) -> bool:
    """Parse explicit boolean string. Reject ambiguous values."""
    v = value.strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"Cannot parse {value!r} as boolean. Use true/false.")


def get_deployment_mode() -> DeploymentMode:
    """Read deployment mode from environment. Fails on unknown values."""
    raw = os.environ.get("DEPLOYMENT_MODE", "internal").strip().lower()
    if raw not in VALID_MODES:
        raise RuntimeError(
            f"Unknown DEPLOYMENT_MODE={raw!r}. Must be one of: {sorted(VALID_MODES)}"
        )
    return raw  # type: ignore[return-value]


def resolve_capabilities(mode: DeploymentMode | None = None) -> dict[Capability, bool]:
    """Resolve all capabilities from mode defaults + env overrides."""
    if mode is None:
        mode = get_deployment_mode()

    defaults = _INTERNAL_DEFAULTS if mode == "internal" else _COMMERCIAL_DEFAULTS
    result = dict(defaults)

    # Apply explicit environment overrides
    for cap, env_var in _ENV_MAP.items():
        raw = os.environ.get(env_var)
        if raw is not None:
            result[cap] = _parse_bool(raw)

    return result


def init_capabilities(app: Flask) -> None:
    """Initialize capability service on the Flask app."""
    mode = get_deployment_mode()
    capabilities = resolve_capabilities(mode)

    # Non-production environments: enable all capabilities by default
    # unless explicitly overridden by env vars. This allows dev/test to
    # access all routes without needing to set every env var.
    if app.config.get("TESTING") or app.config.get("DEBUG"):
        for cap in Capability:
            env_var = _ENV_MAP.get(cap)
            if env_var is None or os.environ.get(env_var) is None:
                capabilities[cap] = True

    app.config["DEPLOYMENT_MODE"] = mode
    app.config["CAPABILITIES"] = capabilities

    # Register template context processor
    @app.context_processor
    def _capability_context() -> dict:
        return {
            "deployment_mode": mode,
            "can": lambda cap: capabilities.get(Capability(cap), False),
            "capabilities": capabilities,
        }


def is_enabled(app: Flask, capability: Capability) -> bool:
    """Check if a capability is enabled. Server-side enforcement."""
    caps = app.config.get("CAPABILITIES")
    if caps is None:
        raise RuntimeError("Capability service not initialized. Call init_capabilities first.")
    return caps.get(capability, False)


def require_capability(app: Flask, capability: Capability) -> None:
    """Raise if capability is disabled. Use in routes for server-side enforcement."""
    if not is_enabled(app, capability):
        from app.core.errors import FeatureDisabledError

        raise FeatureDisabledError(capability.value)
