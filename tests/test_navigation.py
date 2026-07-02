from __future__ import annotations

import pytest


def _client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    Base.metadata.create_all(get_engine(flask_app))
    return flask_app.test_client()


def _login(client):
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.accounts.models import Tenant

    engine = get_engine(database_uri="sqlite:///:memory:")
    with Session(engine) as session:
        tenant = Tenant(company_name="Acme Export")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
    with client.session_transaction() as session_data:
        session_data["tenant_id"] = tenant_id
        session_data["user_id"] = "user-1"


def test_workbench_nav_links_do_not_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    _login(client)

    html = client.get("/workbench").get_data(as_text=True)
    import re

    hrefs = re.findall(r'href="(/[^"]*)"', html)
    nav_hrefs = [h for h in hrefs if h.startswith("/") and not h.startswith("/static")]

    for href in nav_hrefs:
        response = client.get(href)
        assert response.status_code != 404, f"Navigation link {href} returned 404"


def test_find_customers_link_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    _login(client)
    response = client.get("/collection")
    assert response.status_code == 200


def test_crm_link_points_to_leads(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    _login(client)
    html = client.get("/workbench").get_data(as_text=True)
    assert 'href="/leads"' in html
    assert 'href="/crm"' not in html


def test_collect_link_points_to_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    _login(client)
    html = client.get("/workbench").get_data(as_text=True)
    assert 'href="/collection"' in html
    assert 'href="/collect"' not in html


def test_find_customers_header_is_link(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    _login(client)
    html = client.get("/workbench").get_data(as_text=True)
    assert '<a href="/collection" class="lf-button lf-button-primary">' in html


def test_root_redirects_to_workbench_when_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    _login(client)
    response = client.get("/")
    assert response.status_code == 302
    assert "/workbench" in response.headers["Location"]


def test_root_redirects_to_login_when_logged_out(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_404_page_has_go_home_link(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/nonexistent-page-xyz")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert 'href="/"' in html
