from __future__ import annotations

from app.integrations.web.url_safety import SafeUrl


def _safe_example_url(_url: str) -> SafeUrl:
    return SafeUrl(
        canonical_url="https://example.com/dealers",
        host="example.com",
        port=443,
        resolved_ips=("93.184.216.34",),
    )


def test_submit_persists_before_enqueue(browser_app, approved_policy, monkeypatch):
    from app.integrations.browser.service import submit_browser_run

    observed = []

    def fake_enqueue(descriptor_json: str):
        observed.append(descriptor_json)
        return "transport-job-1"

    monkeypatch.setattr("app.integrations.browser.service._enqueue_descriptor", fake_enqueue)
    monkeypatch.setattr(
        "app.integrations.browser.service.validate_browser_public_url", _safe_example_url
    )
    result = submit_browser_run(
        browser_app,
        tenant_id="t1",
        owner_type="smoke",
        owner_id="owner-1",
        requested_url="https://example.com/dealers",
        requested_actions=("read_current_public_page",),
    )
    assert result.status == "queued"
    assert observed
    assert "t1" not in observed[0]


def test_old_attempt_result_cannot_complete_new_attempt(browser_app):
    from app.integrations.browser.service import import_browser_result

    assert (
        import_browser_result(
            browser_app,
            tenant_id="t1",
            run_id="run-1",
            attempt=1,
            result={"run_token": "old-token"},
        ).decision
        == "stale_result_ignored"
    )


def test_import_removes_raw_token_before_persistence(browser_app, approved_policy, monkeypatch):
    import json

    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.integrations.browser.models import BrowserResearchRun
    from app.integrations.browser.service import import_browser_result, submit_browser_run

    observed: list[str] = []
    monkeypatch.setattr(
        "app.integrations.browser.service.validate_browser_public_url", _safe_example_url
    )
    monkeypatch.setattr(
        "app.integrations.browser.service._enqueue_descriptor",
        lambda descriptor_json: observed.append(descriptor_json) or "transport-job-1",
    )
    submitted = submit_browser_run(
        browser_app,
        tenant_id="t1",
        owner_type="smoke",
        owner_id="owner-2",
        requested_url="https://example.com/dealers",
        requested_actions=("read_current_public_page",),
    )
    descriptor = json.loads(observed[0])
    imported = import_browser_result(
        browser_app,
        tenant_id="t1",
        run_id=submitted.run_id,
        attempt=descriptor["attempt"],
        result={
            "run_id": submitted.run_id,
            "run_token": descriptor["run_token"],
            "attempt": descriptor["attempt"],
            "status": "completed",
            "pages": [],
            "page_count": 0,
            "tool_call_count": 0,
            "bytes_written": 0,
        },
    )
    assert imported.decision == "imported"
    with Session(get_engine(browser_app)) as session:
        stored = session.get(BrowserResearchRun, submitted.run_id)
        assert stored is not None
        assert descriptor["run_token"] not in stored.result_json
