from __future__ import annotations

import pytest


def test_browser_repository_requires_matching_tenant(browser_app, db_session):
    from app.integrations.browser.repository import BrowserRunRepository

    repository = BrowserRunRepository(db_session)
    with pytest.raises(ValueError, match="tenant_id is required"):
        repository.get("missing", tenant_id="")


def test_claim_and_completion_are_compare_and_set(browser_app, db_session):
    from app.integrations.browser.models import BrowserResearchRun
    from app.integrations.browser.repository import BrowserRunRepository

    run = BrowserResearchRun(
        id="run-1",
        tenant_id="t1",
        owner_type="smoke",
        owner_id="owner-1",
        requested_url="https://example.com/",
        canonical_domain="example.com",
        run_token_digest="a" * 64,
        budget_json="{}",
    )
    db_session.add(run)
    db_session.commit()
    repository = BrowserRunRepository(db_session)

    assert repository.claim("run-1", tenant_id="t1", lease_seconds=60) == 1
    assert repository.claim("run-1", tenant_id="t1", lease_seconds=60) is None
    assert repository.complete(
        "run-1",
        tenant_id="t1",
        attempt=1,
        run_token_digest="a" * 64,
        status="completed",
        result_json="{}",
        artifact_manifest_json="[]",
    )
    assert not repository.complete(
        "run-1",
        tenant_id="t1",
        attempt=1,
        run_token_digest="a" * 64,
        status="completed",
        result_json="{}",
        artifact_manifest_json="[]",
    )
