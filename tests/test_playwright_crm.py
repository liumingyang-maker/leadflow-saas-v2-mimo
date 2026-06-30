"""Playwright E2E tests for V2-03 CRM browser flows."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.serving import make_server

from app import create_app
from app.config import DevelopmentConfig
from app.extensions import Base, get_engine, reset_engine_for_tests
from app.modules.accounts.admin_service import create_admin
from app.modules.accounts.models import EmailToken

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
sync_playwright = playwright.sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@dataclass(frozen=True)
class LiveServer:
    app: object
    url: str


@pytest.fixture()
def live_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LiveServer]:
    db_path = tmp_path / "playwright-crm.db"
    monkeypatch.setenv("SECRET_KEY", "playwright-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "playwright-tenant-secret-key-that-is-long-enough")
    DevelopmentConfig.SECRET_KEY = os.environ["SECRET_KEY"]
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.as_posix()}"
    DevelopmentConfig.WTF_CSRF_ENABLED = True

    reset_engine_for_tests()
    flask_app = create_app("development")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    create_admin(
        flask_app,
        email="admin@example.com",
        password="admin-password-123",
        must_change_password=False,
    )

    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LiveServer(app=flask_app, url=f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        reset_engine_for_tests()


def test_crm_browser_acceptance(live_server: LiveServer) -> None:
    browser_path = _browser_executable()
    base_host = urlparse(live_server.url).netloc
    console_errors: list[str] = []
    network_hosts: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("request", lambda req: network_hosts.add(urlparse(req.url).netloc))

        _admin_console(page, live_server.url)
        _tenant_signup_login_and_onboarding(page, live_server)

        page.goto(f"{live_server.url}/leads")
        expect(page.locator(".lf-empty-state")).to_contain_text("No leads yet")
        page.goto(f"{live_server.url}/leads/not-real/drawer")
        expect(page.locator("[role='alert']")).to_contain_text("Lead not found")
        console_errors.clear()

        page.goto(f"{live_server.url}/leads/import")
        page.set_input_files(
            "input[name='file']",
            {
                "name": "pilot.csv",
                "mimeType": "text/csv",
                "buffer": b"email,first_name,last_name,title\npilot@example.com,Pilot,Lead,Buyer",
            },
        )
        page.get_by_role("button", name="Preview import").click()
        expect(page.get_by_text("Preview: pilot.csv")).to_be_visible()
        expect(page.get_by_text("1", exact=True).first).to_be_visible()
        page.get_by_role("button", name="Confirm import").click()
        expect(page.get_by_text("Imported 1 leads")).to_be_visible()

        page.goto(f"{live_server.url}/leads")
        lead_link = page.get_by_role("link", name="pilot@example.com")
        lead_link.focus()
        lead_link.click()
        drawer = page.locator("#lead-drawer")
        expect(drawer).to_have_attribute("aria-hidden", "false")
        expect(page.locator("#lead-drawer-content")).to_contain_text("Activity timeline")
        page.wait_for_timeout(250)
        _capture(page, "v2-03-playwright-desktop.png")

        page.keyboard.press("Escape")
        expect(drawer).to_have_attribute("aria-hidden", "true")
        page.wait_for_timeout(300)
        assert page.evaluate("document.activeElement.textContent.trim()") == "pilot@example.com"

        page.goto(f"{live_server.url}/leads")
        detail_href = page.get_by_role("link", name="pilot@example.com").get_attribute("href")
        page.goto(f"{live_server.url}{detail_href}")
        page.locator("select[name='stage']").select_option("qualified")
        page.get_by_role("button", name="Update stage").click()
        page.wait_for_load_state("networkidle")
        page.goto(f"{live_server.url}/leads")
        expect(page.get_by_text("qualified", exact=True)).to_be_visible()

        page.get_by_role("link", name="pilot@example.com").click()
        page.locator("#drawer-note").fill("Interested in a demo")
        page.get_by_role("button", name="Save note").click()
        page.wait_for_load_state("networkidle")
        page.goto(f"{live_server.url}/leads")
        page.get_by_role("link", name="pilot@example.com").click()
        page.locator("#drawer-tag-name").fill("Hot")
        page.get_by_role("button", name="Add").click()
        page.wait_for_load_state("networkidle")
        page.goto(f"{live_server.url}/leads")
        page.get_by_role("link", name="pilot@example.com").click()
        expect(page.locator(".lf-notes")).to_contain_text("Interested in a demo")
        expect(page.locator(".lf-drawer-body")).to_contain_text("Hot")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{live_server.url}/leads")
        page.get_by_role("link", name="pilot@example.com").click()
        expect(drawer).to_have_attribute("aria-hidden", "false")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.wait_for_timeout(250)
        _capture(page, "v2-03-playwright-mobile.png")

        browser.close()

    assert not console_errors
    assert network_hosts <= {base_host}


def _tenant_signup_login_and_onboarding(page, live_server: LiveServer) -> None:
    base_url = live_server.url
    page.goto(f"{base_url}/register")
    expect(page.get_by_role("heading", name="Create a LeadFlow tenant")).to_be_visible()
    page.locator("input[name='company_name']").fill("Playwright Co")
    page.locator("input[name='email']").fill("owner@example.com")
    page.locator("input[name='password']").fill("safe-password-123")
    page.get_by_role("button", name="Create tenant").click()
    expect(page.get_by_role("heading", name="Sign in to LeadFlow")).to_be_visible()

    token = _verification_token(live_server)
    page.goto(f"{base_url}/verify-email/{token}")
    page.locator("input[name='email']").fill("owner@example.com")
    page.locator("input[name='password']").fill("safe-password-123")
    page.get_by_role("button", name="Continue").click()
    expect(page).to_have_url(f"{base_url}/workbench")

    page.goto(f"{base_url}/onboarding")
    expect(page.get_by_role("heading", name="Set up your workspace")).to_be_visible()
    page.locator("input[name='industry']").fill("SaaS")
    page.get_by_role("button", name="Complete setup").click()
    expect(page).to_have_url(f"{base_url}/workbench")


def _admin_console(page, base_url: str) -> None:
    page.goto(f"{base_url}/admin/login")
    page.locator("input[name='email']").fill("admin@example.com")
    page.locator("input[name='password']").fill("admin-password-123")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("heading", name="Admin console")).to_be_visible()


def _verification_token(live_server: LiveServer) -> str:
    engine = get_engine(live_server.app)
    with Session(engine) as session:
        return session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()


def _browser_executable() -> str | None:
    env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if env_path:
        return env_path
    if EDGE.exists():
        return str(EDGE)
    pytest.skip("No local Chromium or Edge executable available for Playwright")


def _capture(page, filename: str) -> None:
    if os.environ.get("LEADFLOW_CAPTURE_SCREENSHOTS") != "1":
        return
    target = ROOT / ".autopilot" / "evidence" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=True)
