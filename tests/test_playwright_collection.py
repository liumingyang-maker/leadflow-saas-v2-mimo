"""Playwright smoke test for the V2-04 collection workspace."""

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
from app.modules.jobs.models import Job

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
    db_path = tmp_path / "playwright-collection.db"
    monkeypatch.setenv("SECRET_KEY", "playwright-secret-key-that-is-long-enough")
    DevelopmentConfig.SECRET_KEY = os.environ["SECRET_KEY"]
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.as_posix()}"
    DevelopmentConfig.WTF_CSRF_ENABLED = True

    reset_engine_for_tests()
    flask_app = create_app("development")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        tenant = Tenant(company_name="Collection Co")
        user = User(
            email="collector@example.com",
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.commit()

    def fake_create_and_enqueue(app, *, tenant_id, job_type, payload=None, queue_name="default"):
        with Session(get_engine(app)) as session:
            job = Job(
                tenant_id=tenant_id,
                job_type=job_type,
                status="succeeded",
                progress=100,
                progress_message="Collection completed",
                payload_json="{}",
                result_summary_json='{"found": 2, "created": 2}',
                queue_name=queue_name,
                rq_job_id="playwright-rq",
                queued_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    monkeypatch.setattr("app.modules.jobs.routes.create_and_enqueue", fake_create_and_enqueue)

    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LiveServer(app=flask_app, url=f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        reset_engine_for_tests()


def test_collection_browser_acceptance(live_server: LiveServer) -> None:
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

        _login(page, live_server.url)
        page.goto(f"{live_server.url}/collection")
        expect(page.get_by_role("heading", name="Collection workspace")).to_be_visible()
        expect(page.locator(".lf-empty-state")).to_contain_text("No jobs yet")

        page.get_by_role("link", name="Google Search").click()
        expect(page.get_by_role("heading", name="Google Search")).to_be_visible()
        page.locator("input[name='query']").fill("b2b data vendors")
        page.get_by_role("button", name="Start collection").click()
        expect(page.get_by_role("heading", name="google_search")).to_be_visible()
        expect(page.locator("#job-status-container")).to_contain_text("succeeded")
        expect(page.locator("#job-status-container")).to_contain_text("100%")
        _capture(page, "v2-04-collection-desktop.png")

        page.goto(f"{live_server.url}/collection/maps")
        page.locator("input[name='query']").fill("accounting firms")
        page.locator("input[name='location']").fill("Austin, TX")
        page.get_by_role("button", name="Start collection").click()
        expect(page.get_by_role("heading", name="google_maps")).to_be_visible()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{live_server.url}/collection")
        expect(page.get_by_role("heading", name="Collection workspace")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        _capture(page, "v2-04-collection-mobile.png")
        browser.close()

    assert not console_errors
    assert network_hosts <= {base_host}


def _login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login")
    page.locator("input[name='email']").fill("collector@example.com")
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
    target = ROOT / ".autopilot" / "evidence" / "V2-04" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=True)
