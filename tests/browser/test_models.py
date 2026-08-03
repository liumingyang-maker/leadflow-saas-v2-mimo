from __future__ import annotations


def test_browser_run_stores_digest_and_bounded_owner(browser_app, db_session):
    from app.integrations.browser.models import BrowserResearchRun

    run = BrowserResearchRun(
        tenant_id="t1",
        owner_type="radar_run",
        owner_id="owner-1",
        requested_url="https://example.com/dealers?token=secret",
        canonical_domain="example.com",
        run_token_digest="a" * 64,
        budget_json='{"max_pages":3,"max_seconds":120,"max_tool_calls":12}',
    )
    db_session.add(run)
    db_session.commit()

    assert run.status == "queued"
    assert "token=secret" not in run.requested_url
    assert not hasattr(run, "run_token")


def test_policy_defaults_to_review_safe_values(browser_app, db_session):
    from app.integrations.browser.models import BrowserSitePolicy

    policy = BrowserSitePolicy(tenant_id="t1", canonical_domain="example.com")
    db_session.add(policy)
    db_session.commit()

    assert policy.access_mode == "review_required"
    assert policy.terms_status == "unknown"
    assert policy.robots_status == "unknown"
