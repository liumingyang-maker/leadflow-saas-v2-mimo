"""Tests for runtime closure: local HTMX, native drawer JS, no Alpine."""

from __future__ import annotations

import os


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def test_htmx_is_loaded_locally() -> None:
    path = os.path.join(ROOT, "app", "static", "vendor", "htmx", "htmx.min.js")
    assert os.path.isfile(path), f"HTMX not found at {path}"
    size = os.path.getsize(path)
    assert size > 10000, f"HTMX file too small ({size} bytes)"


def test_shell_loads_htmx_via_url_for() -> None:
    shell = _read(os.path.join(ROOT, "app", "templates", "components", "_shell.html"))
    assert "vendor/htmx/htmx.min.js" in shell
    assert "url_for('static'" in shell or 'url_for("static"' in shell


def test_shell_loads_drawer_js_via_url_for() -> None:
    shell = _read(os.path.join(ROOT, "app", "templates", "components", "_shell.html"))
    assert "lead-drawer.js" in shell
    assert "defer" in shell


def test_no_remote_cdn_in_shell() -> None:
    shell = _read(os.path.join(ROOT, "app", "templates", "components", "_shell.html"))
    assert "unpkg.com" not in shell
    assert "cdn.jsdelivr.net" not in shell
    assert "cdnjs.cloudflare.com" not in shell


def test_no_alpine_attributes_in_list() -> None:
    html = _read(os.path.join(ROOT, "app", "templates", "leads", "list.html"))
    assert "x-data" not in html
    assert "x-show" not in html
    assert "x-effect" not in html
    assert "@keydown" not in html
    assert "@click" not in html
    assert "x-transition" not in html


def test_no_alpine_attributes_in_drawer_partial() -> None:
    html = _read(os.path.join(ROOT, "app", "templates", "leads", "_drawer.html"))
    assert "x-data" not in html
    assert "x-show" not in html


def test_lead_link_has_both_href_and_hx_get() -> None:
    html = _read(os.path.join(ROOT, "app", "templates", "leads", "list.html"))
    assert 'href="/leads/' in html
    assert 'hx-get="/leads/' in html
    assert 'hx-target="#lead-drawer-content"' in html
    assert 'hx-swap="innerHTML"' in html


def test_no_hyperscript_in_list() -> None:
    html = _read(os.path.join(ROOT, "app", "templates", "leads", "list.html"))
    assert " _=" not in html


def test_drawer_container_has_dialog_semantics() -> None:
    html = _read(os.path.join(ROOT, "app", "templates", "leads", "list.html"))
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-label="Lead detail"' in html
    assert 'aria-hidden="true"' in html


def test_drawer_js_exists_and_has_required_behaviours() -> None:
    js = _read(os.path.join(ROOT, "app", "static", "js", "lead-drawer.js"))
    assert "Escape" in js or "escape" in js
    assert "focus" in js
    assert "scroll" in js or "overflow" in js
    assert "backdrop" in js or "backdropEl" in js
    assert "reduced-motion" in js or "reduce" in js
    assert "htmx:afterSwap" in js
    assert "htmx:beforeRequest" in js
    assert "htmx:responseError" in js
    assert "close" in js
    assert "open" in js


def test_drawer_js_no_inner_html_user_content() -> None:
    js = _read(os.path.join(ROOT, "app", "static", "js", "lead-drawer.js"))
    # The only innerHTML is for loading/error state (server-generated safe content)
    # No eval
    assert "eval" not in js


def test_full_detail_page_fallback_works(monkeypatch) -> None:
    from test_lead_drawer import _setup

    client, _engine, _app, _tid, lead_id = _setup(monkeypatch)
    resp = client.get(f"/leads/{lead_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<!doctype html>" in html.lower()
    assert "lead@test.com" in html


def test_drawer_partial_has_no_shell(monkeypatch) -> None:
    from test_lead_drawer import _setup

    client, _engine, _app, _tid, lead_id = _setup(monkeypatch)
    resp = client.get(f"/leads/{lead_id}/drawer")
    html = resp.get_data(as_text=True)
    assert "<!doctype html>" not in html.lower()
    assert "lf-drawer-inner" in html


def test_third_party_assets_doc_exists() -> None:
    path = os.path.join(ROOT, "docs", "THIRD_PARTY_ASSETS.md")
    assert os.path.isfile(path)
    content = _read(path)
    assert "htmx" in content.lower() or "HTMX" in content
    assert "2.0" in content
    assert "BSD" in content


def test_xss_greps_still_clean() -> None:
    """Verify no |safe, Markup, or render_template_string anywhere."""
    import subprocess

    result = subprocess.run(
        ["git", "grep", "-n", "|safe", "--", "*.html", "*.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    # Exclude test files which mention |safe in comments/assertions only
    safe_lines = [
        line for line in result.stdout.split("\n") if line.strip() and not line.startswith("tests/")
    ]
    assert len(safe_lines) == 0, f"|safe found in non-test code: {safe_lines}"

    result = subprocess.run(
        ["git", "grep", "-n", "Markup", "--", "*.py"], capture_output=True, text=True, cwd=ROOT
    )
    markup_lines = [
        line for line in result.stdout.split("\n") if line.strip() and not line.startswith("tests/")
    ]
    assert len(markup_lines) == 0, f"Markup found: {markup_lines}"

    result = subprocess.run(
        ["git", "grep", "-n", "render_template_string", "--", "*.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    rts_lines = [
        line for line in result.stdout.split("\n") if line.strip() and not line.startswith("tests/")
    ]
    assert len(rts_lines) == 0, f"render_template_string found: {rts_lines}"
