"""Playwright smoke for V2-05 outreach and inbound pages."""

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
from app.modules.accounts.models import Tenant, TenantMembership, User
from app.modules.leads.models import Lead

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
sync_playwright = playwright.sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@dataclass(frozen=True)
class LiveServer:
    app: object
    url: str
    lead_id: str


@pytest.fixture()
def live_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LiveServer]:
    db_path = tmp_path / "playwright-v2-05.db"
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
        tenant = Tenant(company_name="Playwright Outreach")
        user = User(
            email="owner@example.com",
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.flush()
        lead = Lead(
            tenant_id=tenant.id,
            email="lead@example.com",
            first_name="Lead",
            last_name="Buyer",
            source="manual",
            status="accepted",
        )
        session.add(lead)
        session.commit()
        lead_id = lead.id

    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LiveServer(
            app=flask_app, url=f"http://127.0.0.1:{server.server_port}", lead_id=lead_id
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        reset_engine_for_tests()


def test_outreach_inbound_browser_acceptance(live_server: LiveServer) -> None:
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

        _login(page, live_server.url)
        page.goto(f"{live_server.url}/outreach")
        expect(page.get_by_role("heading", name="Outreach")).to_be_visible()

        page.goto(f"{live_server.url}/outreach/templates")
        page.locator("input[name='name']").fill("Intro")
        page.locator("input[name='subject']").fill("Quick hello")
        page.locator("textarea[name='body_text']").fill("Hello from LeadFlow.")
        page.get_by_role("button", name="Create template").click()
        expect(page.get_by_text("Intro")).to_be_visible()

        page.goto(f"{live_server.url}/leads/{live_server.lead_id}/outreach")
        page.locator("input[name='subject']").fill("Quick hello")
        page.locator("textarea[name='body_text']").fill("Hello from LeadFlow.")
        page.get_by_role("button", name="Send").click()
        expect(page.get_by_text("sent", exact=True)).to_be_visible()
        _capture(page, "v2-05-outreach-desktop.png")

        page.goto(f"{live_server.url}/inbound")
        expect(page.get_by_role("heading", name="Inbound API")).to_be_visible()
        page.locator("input[name='origin']").fill("https://site.example")
        page.get_by_role("button", name="Add origin").click()
        expect(page.get_by_text("https://site.example")).to_be_visible()
        page.get_by_role("button", name="Generate / Regenerate token").click()
        expect(page.get_by_text("New token:")).to_be_visible()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{live_server.url}/outreach")
        expect(page.get_by_role("heading", name="Outreach")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.goto(f"{live_server.url}/inbound")
        expect(page.get_by_role("heading", name="Inbound API")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        _capture(page, "v2-05-inbound-mobile.png")
        browser.close()

    assert not console_errors
    assert network_hosts <= {base_host}


def _login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login")
    page.locator("input[name='email']").fill("owner@example.com")
    page.locator("input[name='password']").fill("safe-password-123")
    page.get_by_role("button", name="Continue").click()
    expect(page).to_have_url(f"{base_url}/workbench")


def _browser_executable() -> str | None:
    env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if env_path:
        return env_path
    if EDGE.exists():
        return str(EDGE)
    pytest.skip("No local Chromium or Edge executable available for Playwright")


def _capture(page, filename: str) -> None:
    target = ROOT / ".autopilot" / "evidence" / "V2-05" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=True)
