from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_plan_forbids_evaluate_form_upload_and_download() -> None:
    from app.integrations.browser.contracts import BrowserResearchPlan

    for forbidden in ("evaluate", "fill", "submit", "upload", "download"):
        with pytest.raises(ValidationError):
            BrowserResearchPlan.model_validate(
                {
                    "version": "browser-plan-v1",
                    "start_url": "https://example.com/dealers",
                    "allowed_origins": ["https://example.com"],
                    "actions": [{"tool": forbidden}],
                }
            )


def test_final_navigation_rejects_cross_origin_redirect() -> None:
    from app.integrations.browser.policy import BrowserPolicyError, validate_navigation

    with pytest.raises(BrowserPolicyError, match="origin_not_allowed"):
        validate_navigation(
            requested_url="https://example.com/dealers",
            final_url="https://attacker.example/path",
            allowed_origins=("https://example.com",),
            resolver=lambda host: ["93.184.216.34"] if host == "example.com" else ["8.8.8.8"],
        )


def test_browser_navigation_rejects_http_non_443_and_fragments() -> None:
    from app.integrations.browser.policy import BrowserPolicyError, validate_navigation

    for url in (
        "http://example.com/path",
        "https://example.com:8443/path",
        "https://example.com/path#access_token=secret",
    ):
        with pytest.raises(BrowserPolicyError):
            validate_navigation(
                requested_url="https://example.com/",
                final_url=url,
                allowed_origins=("https://example.com",),
                resolver=lambda _host: ["93.184.216.34"],
            )


def test_unknown_or_prohibited_site_never_auto_approves() -> None:
    from app.integrations.browser.policy import evaluate_site_policy

    unknown = evaluate_site_policy(None, requested_url="https://example.com/")
    prohibited = evaluate_site_policy(None, requested_url="https://www.linkedin.com/company/x")

    assert unknown.decision == "review_required"
    assert prohibited.decision == "blocked"
    assert prohibited.reason_code == "system_blocked"
