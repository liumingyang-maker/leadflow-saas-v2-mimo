"""Executable V2-06 browser acceptance smoke."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from app import create_app
from app.config import DevelopmentConfig
from app.extensions import Base, get_engine, reset_engine_for_tests
from app.modules.accounts.models import AdminUser, Tenant, TenantMembership, User
from app.modules.audit.service import record_event

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
sync_playwright = playwright.sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@dataclass(frozen=True)
class LiveServer:
    url: str


@pytest.fixture()
def live_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LiveServer]:
    db_path = tmp_path / "playwright-v2-06.db"
    monkeypatch.setenv("SECRET_KEY", "playwright-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "playwright-tenant-secret-key-that-is-long-enough")
    DevelopmentConfig.SECRET_KEY = os.environ["SECRET_KEY"]
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.as_posix()}"
    DevelopmentConfig.WTF_CSRF_ENABLED = True

    reset_engine_for_tests()
    flask_app = create_app("development")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tenant = Tenant(company_name="Launch Tenant", industry="B2B", status="active")
        user = User(
            email="owner@example.com",
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        admin = AdminUser(
            email="admin@example.com",
            password_hash=generate_password_hash("temporary-safe-password-123"),
            must_change_password=False,
        )
        session.add_all([TenantMembership(tenant=tenant, user=user, role="owner"), admin])
        session.commit()
        tenant_id = tenant.id
        user_id = user.id

    with flask_app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "playwright"}
    ):
        record_event(
            flask_app,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="launch_checked",
            target_type="tenant",
            target_id=tenant_id,
            safe_summary="Launch browser smoke event",
        )

    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LiveServer(url=f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        reset_engine_for_tests()


def test_launch_browser_acceptance(live_server: LiveServer) -> None:
    browser_path = _browser_executable()
    base_host = urlparse(live_server.url).netloc
    console_errors: list[str] = []
    network_hosts: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("request", lambda req: network_hosts.add(urlparse(req.url).netloc))

        _login_tenant(page, live_server.url)
        page.goto(f"{live_server.url}/settings")
        expect(page.get_by_role("heading", name="Workspace settings")).to_be_visible()
        _capture(page, "v2-06-settings-desktop.png")

        page.goto(f"{live_server.url}/audit")
        expect(page.get_by_role("heading", name="Audit log")).to_be_visible()
        expect(page.get_by_text("Launch browser smoke event")).to_be_visible()

        page.goto(f"{live_server.url}/admin/system")
        expect(page).to_have_url(f"{live_server.url}/admin/login")

        _login_admin(page, live_server.url)
        page.goto(f"{live_server.url}/admin/system")
        expect(page.get_by_role("heading", name="System diagnostics")).to_be_visible()
        page.goto(f"{live_server.url}/admin/audit")
        expect(page.get_by_role("heading", name="System audit")).to_be_visible()
        assert not console_errors

        console_errors.clear()
        missing = page.goto(f"{live_server.url}/does-not-exist-v2-06")
        assert missing is not None
        assert missing.status == 404
        expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
        console_errors.clear()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{live_server.url}/admin/system")
        expect(page.get_by_role("heading", name="System diagnostics")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        _capture(page, "v2-06-admin-system-mobile.png")
        browser.close()

    assert not console_errors
    assert network_hosts <= {base_host}


def _login_tenant(page, base_url: str) -> None:
    page.goto(f"{base_url}/login")
    page.locator("input[name='email']").fill("owner@example.com")
    page.locator("input[name='password']").fill("safe-password-123")
    page.get_by_role("button", name="Continue").click()
    expect(page).to_have_url(f"{base_url}/workbench")


def _login_admin(page, base_url: str) -> None:
    page.goto(f"{base_url}/admin/login")
    page.locator("input[name='email']").fill("admin@example.com")
    page.locator("input[name='password']").fill("temporary-safe-password-123")
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(f"{base_url}/admin")


def _browser_executable() -> str | None:
    env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if env_path:
        return env_path
    if EDGE.exists():
        return str(EDGE)
    pytest.skip("No local Chromium or Edge executable available for Playwright")


def _capture(page, filename: str) -> None:
    target = ROOT / ".autopilot" / "evidence" / "V2-06" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=True)
