from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_signal_workspace_tokens_are_defined() -> None:
    tokens = (ROOT / "app" / "static" / "css" / "tokens.css").read_text(encoding="utf-8")

    for token in [
        "--lf-canvas: #F5F7FA",
        "--lf-surface: #FFFFFF",
        "--lf-text-strong: #152033",
        "--lf-primary: #246BFD",
        "--lf-signal: #00A8C6",
        "--lf-danger: #C83B48",
        "--lf-sidebar-width: 240px",
    ]:
        assert token in tokens

    assert "linear-gradient" not in tokens
    assert "#7c3aed" not in tokens.lower()


def test_component_macros_and_motion_rules_exist() -> None:
    component_dir = ROOT / "app" / "templates" / "components"
    expected = [
        "_buttons.html",
        "_forms.html",
        "_badges.html",
        "_empty_states.html",
        "_shell.html",
    ]

    for name in expected:
        assert (component_dir / name).is_file()

    components_css = (ROOT / "app" / "static" / "css" / "components.css").read_text(
        encoding="utf-8"
    )
    assert "prefers-reduced-motion" in components_css
    assert "transition: all" not in components_css
    assert "focus-visible" in components_css


def test_design_system_preview_renders_accessible_core_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app

    response = create_app("testing").test_client().get("/_design-system")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a class="lf-skip-link" href="#main">' in html
    assert "Signal Workspace" in html
    assert 'aria-live="polite"' in html
    assert 'for="demo-email"' in html
    assert 'aria-label="Open filters"' in html
    assert "No accepted leads yet" in html
    assert "Loading…" in html
    assert "Unable to load leads" in html


def test_design_system_document_records_ui_audit_contract() -> None:
    doc = (ROOT / "docs" / "design-system" / "SIGNAL_WORKSPACE.md").read_text(encoding="utf-8")

    for phrase in [
        "Signal Workspace",
        "WCAG 2.2 AA",
        "No purple AI gradients",
        "Corporate motion",
        "desktop and 375px mobile screenshots",
    ]:
        assert phrase in doc
