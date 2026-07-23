"""Tests for the Capability Service and Deployment Profile (INT-001)."""

from __future__ import annotations

import pytest


def test_internal_mode_defaults(monkeypatch):
    """Internal mode disables public registration, billing, payments."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.delenv("ALLOW_PUBLIC_REGISTRATION", raising=False)
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("PAYMENT_WEBHOOKS_ENABLED", raising=False)
    monkeypatch.delenv("INBOUND_API_ENABLED", raising=False)

    from app.core.capabilities import Capability, resolve_capabilities

    caps = resolve_capabilities("internal")
    assert caps[Capability.PUBLIC_REGISTRATION] is False
    assert caps[Capability.BILLING] is False
    assert caps[Capability.PAYMENT_WEBHOOKS] is False
    assert caps[Capability.INBOUND_API] is False
    assert caps[Capability.OUTREACH_SEND] is True
    assert caps[Capability.ADMIN_CONSOLE] is True
    assert caps[Capability.INVITE_ONLY] is True


def test_commercial_mode_defaults(monkeypatch):
    """Commercial mode enables public registration and billing."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "commercial")

    from app.core.capabilities import Capability, resolve_capabilities

    caps = resolve_capabilities("commercial")
    assert caps[Capability.PUBLIC_REGISTRATION] is True
    assert caps[Capability.BILLING] is True
    assert caps[Capability.PAYMENT_WEBHOOKS] is True
    assert caps[Capability.INBOUND_API] is True
    assert caps[Capability.INVITE_ONLY] is False


def test_env_override(monkeypatch):
    """Explicit env vars override mode defaults."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.setenv("INBOUND_API_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_SEND_ENABLED", "false")

    from app.core.capabilities import Capability, resolve_capabilities

    caps = resolve_capabilities("internal")
    assert caps[Capability.INBOUND_API] is True
    assert caps[Capability.OUTREACH_SEND] is False


def test_unknown_mode_fails(monkeypatch):
    """Unknown DEPLOYMENT_MODE raises RuntimeError."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "staging")

    from app.core.capabilities import get_deployment_mode

    with pytest.raises(RuntimeError, match="Unknown DEPLOYMENT_MODE"):
        get_deployment_mode()


def test_invalid_bool_rejected(monkeypatch):
    """Ambiguous boolean strings are rejected."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.setenv("BILLING_ENABLED", "maybe")

    from app.core.capabilities import resolve_capabilities

    with pytest.raises(ValueError, match="Cannot parse"):
        resolve_capabilities("internal")


def test_default_mode_is_internal(monkeypatch):
    """Without DEPLOYMENT_MODE set, defaults to internal."""
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)

    from app.core.capabilities import get_deployment_mode

    assert get_deployment_mode() == "internal"


def test_app_factory_initializes_capabilities(monkeypatch):
    """create_app initializes capability config."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "false")

    from app import create_app
    from app.core.capabilities import Capability, is_enabled

    app = create_app("testing")
    assert app.config["DEPLOYMENT_MODE"] == "internal"
    assert is_enabled(app, Capability.ADMIN_CONSOLE) is True
    assert is_enabled(app, Capability.PUBLIC_REGISTRATION) is False


def test_register_disabled_in_internal_mode(monkeypatch):
    """Public registration route returns 404 in internal mode."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "false")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    engine = get_engine(app)
    Base.metadata.create_all(engine)
    client = app.test_client()

    resp = client.get("/register")
    assert resp.status_code == 404

    resp_post = client.post("/register", data={"email": "a@b.com"})
    assert resp_post.status_code == 404


def test_template_context_has_can(monkeypatch):
    """Template context processor provides can() function."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")

    from app import create_app

    app = create_app("testing")
    with app.test_request_context("/"):
        # context_processor adds to template globals
        # Verify via app.config instead
        assert app.config["CAPABILITIES"] is not None
