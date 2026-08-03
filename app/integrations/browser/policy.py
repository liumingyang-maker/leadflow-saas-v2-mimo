from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from app.integrations.web.url_safety import (
    Resolver,
    SafeUrl,
    UnsafeUrlError,
    validate_browser_public_url,
)


class BrowserPolicyError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SitePolicyValues(Protocol):
    access_mode: str
    terms_status: str
    robots_status: str


@dataclass(frozen=True)
class BrowserPolicyDecision:
    decision: str
    reason_code: str


SYSTEM_BLOCKED_DOMAINS = frozenset({"linkedin.com"})


def _canonical_host(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").rstrip(".").lower()
    except ValueError:
        return ""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def _is_system_blocked(host: str) -> bool:
    return any(
        host == blocked or host.endswith(f".{blocked}") for blocked in SYSTEM_BLOCKED_DOMAINS
    )


def evaluate_site_policy(
    site_policy: SitePolicyValues | None, *, requested_url: str
) -> BrowserPolicyDecision:
    """Return the immutable policy decision without doing network I/O."""

    host = _canonical_host(requested_url)
    if _is_system_blocked(host):
        return BrowserPolicyDecision("blocked", "system_blocked")
    try:
        parsed = urlsplit(requested_url)
        is_https_443 = parsed.scheme.lower() == "https" and parsed.port in {None, 443}
    except ValueError:
        is_https_443 = False
    if not is_https_443:
        return BrowserPolicyDecision("blocked", "https_required")
    if site_policy is None:
        return BrowserPolicyDecision("review_required", "unknown_site")
    if site_policy.terms_status == "rejected" or site_policy.robots_status == "disallowed":
        return BrowserPolicyDecision("blocked", "terms_or_robots_rejected")
    if site_policy.access_mode in {"blocked", "manual_only"}:
        return BrowserPolicyDecision("blocked", "tenant_policy_blocked")
    if site_policy.access_mode == "review_required":
        return BrowserPolicyDecision("review_required", "tenant_review_required")
    if site_policy.access_mode == "auto_public":
        if site_policy.terms_status == "approved" and site_policy.robots_status == "allowed":
            return BrowserPolicyDecision("approved", "auto_public_approved")
        return BrowserPolicyDecision("review_required", "approval_incomplete")
    return BrowserPolicyDecision("review_required", "unknown_policy_state")


def _origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        host = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        raise BrowserPolicyError("origin_not_allowed") from None
    return f"https://{host}"


def _path_allowed(path: str, allowed_paths: tuple[str, ...]) -> bool:
    for allowed in allowed_paths:
        root = allowed.rstrip("/") or "/"
        if root == "/" or path == root or path.startswith(f"{root}/"):
            return True
    return False


def validate_navigation(
    *,
    requested_url: str,
    final_url: str,
    allowed_origins: tuple[str, ...],
    allowed_paths: tuple[str, ...] = ("/",),
    resolver: Resolver,
) -> SafeUrl:
    """Validate both ends of a redirect and return a DNS-pinned final URL."""

    try:
        requested = validate_browser_public_url(requested_url, resolver=resolver)
        final = validate_browser_public_url(final_url, resolver=resolver)
    except UnsafeUrlError as exc:
        raise BrowserPolicyError("navigation_url_blocked") from exc
    allowed = {_origin(value) for value in allowed_origins}
    if requested.origin not in allowed or final.origin not in allowed:
        raise BrowserPolicyError("origin_not_allowed")
    final_path = urlsplit(final.canonical_url).path or "/"
    if not _path_allowed(final_path, allowed_paths):
        raise BrowserPolicyError("path_not_allowed")
    return final
