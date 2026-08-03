"""Safe, deterministic planning and persistence for Radar page snapshots."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.web.fetcher import FetchResult
from app.integrations.web.url_safety import Resolver, UnsafeUrlError, system_resolver
from app.modules.radar.models import CompetitorProfile, RadarRun, RadarSnapshot
from app.modules.radar.policies import (
    RadarPolicyError,
    canonical_json,
    canonical_public_url,
    parse_bounded_json_object,
)

RADAR_STATIC_EXTRACTOR_VERSION = "radar-static-v1"
_ALLOWED_PAGE_KINDS = frozenset(
    {"home", "product", "dealers", "partners", "contact", "about", "other"}
)
_DYNAMIC_SHELL_MARKERS = (
    "enable javascript",
    "javascript required",
    "javascript is required",
    "please enable javascript",
)
_PAGE_KIND_PATTERNS = (
    ("dealers", ("dealer", "distributor", "distribuidor", "经销", "分销")),
    ("partners", ("partner", "合作伙伴", "partenaire", "socio")),
    ("product", ("product", "products", "producto", "产品", "solution")),
    ("contact", ("contact", "contacto", "联系")),
    ("about", ("about", "company", "empresa", "关于")),
)


class RadarSnapshotError(ValueError):
    """A page is not safe or valid for a Radar Run."""


@dataclass(frozen=True)
class PlannedRadarPage:
    requested_url: str
    canonical_url: str
    page_kind: str
    anchor_text: str = ""


def plan_radar_pages(
    *,
    official_url: str,
    canonical_domain: str,
    tracking_config_json: str,
    observed_links: tuple[dict[str, str], ...] | tuple[tuple[str, str], ...] = (),
    page_limit: int,
    resolver: Resolver = system_resolver,
) -> tuple[PlannedRadarPage, ...]:
    """Return deterministic, same-domain page plans for one manual Run.

    The homepage is always first. Configured URLs are explicit user choices; observed
    URLs can only be same-domain links produced by a successful static fetch.
    """

    bounded_limit = max(1, min(int(page_limit), 25))
    try:
        home = canonical_public_url(official_url, resolver=resolver)
    except UnsafeUrlError as exc:
        raise RadarSnapshotError("Competitor homepage is not a public URL") from exc
    if home.host != canonical_domain:
        raise RadarSnapshotError("Competitor homepage does not match its canonical domain")

    planned: list[PlannedRadarPage] = [
        PlannedRadarPage(home.canonical_url, home.canonical_url, "home")
    ]
    seen = {home.canonical_url}
    config = _tracking_config(tracking_config_json)
    for item in config.get("seed_pages", []):
        if len(planned) >= bounded_limit:
            break
        if not isinstance(item, dict):
            raise RadarSnapshotError("Configured Radar page must be an object")
        page_kind = item.get("page_kind")
        requested_url = item.get("url")
        if not isinstance(page_kind, str) or page_kind not in _ALLOWED_PAGE_KINDS:
            raise RadarSnapshotError("Configured Radar page kind is not allowed")
        if not isinstance(requested_url, str) or not requested_url.strip():
            raise RadarSnapshotError("Configured Radar page URL is required")
        candidate = _same_domain_url(
            requested_url,
            base_url=home.canonical_url,
            canonical_domain=canonical_domain,
            resolver=resolver,
            reject_foreign=True,
        )
        if candidate is not None:
            _append_plan(planned, seen, candidate, page_kind, "")

    for item in observed_links:
        if len(planned) >= bounded_limit:
            break
        requested_url, anchor_text = _observed_link_values(item)
        if not requested_url:
            continue
        candidate = _same_domain_url(
            requested_url,
            base_url=home.canonical_url,
            canonical_domain=canonical_domain,
            resolver=resolver,
            reject_foreign=False,
        )
        if candidate is not None:
            page_kind = _classify_page(candidate, anchor_text)
            _append_plan(
                planned,
                seen,
                candidate,
                page_kind,
                anchor_text,
            )
    return tuple(planned)


def finalize_snapshot(
    session: Session,
    *,
    profile_id: str,
    run_id: str,
    page_kind: str,
    fetched_page: FetchResult,
) -> RadarSnapshot:
    """Persist one sanitized fetch result or return its prior immutable equivalent."""

    if page_kind not in _ALLOWED_PAGE_KINDS:
        raise RadarSnapshotError("Radar page kind is not allowed")
    profile = session.get(CompetitorProfile, profile_id)
    run = session.get(RadarRun, run_id)
    if profile is None or run is None or run.profile_id != profile.id:
        raise RadarSnapshotError("Radar Run does not own this profile")
    if profile.tenant_id != run.tenant_id:
        raise RadarSnapshotError("Radar Run tenant does not match its profile")

    facts_json, excerpt, validation_status = _structured_snapshot(fetched_page)
    existing = session.scalar(
        select(RadarSnapshot).where(
            RadarSnapshot.tenant_id == profile.tenant_id,
            RadarSnapshot.profile_id == profile.id,
            RadarSnapshot.canonical_url == fetched_page.final_url,
            RadarSnapshot.content_hash == fetched_page.content_hash,
        )
    )
    if existing is not None:
        return existing

    snapshot = RadarSnapshot(
        tenant_id=profile.tenant_id,
        profile_id=profile.id,
        run_id=run.id,
        page_kind=page_kind,
        requested_url=fetched_page.requested_url[:1000],
        canonical_url=fetched_page.final_url[:1000],
        content_hash=fetched_page.content_hash,
        facts_json=facts_json,
        excerpt=excerpt,
        source_method="static",
        validation_status=validation_status,
        extractor_version=RADAR_STATIC_EXTRACTOR_VERSION,
        observed_at=fetched_page.retrieved_at,
    )
    try:
        with session.begin_nested():
            session.add(snapshot)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(RadarSnapshot).where(
                RadarSnapshot.tenant_id == profile.tenant_id,
                RadarSnapshot.profile_id == profile.id,
                RadarSnapshot.canonical_url == fetched_page.final_url,
                RadarSnapshot.content_hash == fetched_page.content_hash,
            )
        )
        if existing is not None:
            return existing
        raise
    return snapshot


def finalize_unreachable_snapshot(
    session: Session,
    *,
    profile_id: str,
    run_id: str,
    page_kind: str,
    requested_url: str,
    canonical_url: str,
    reason_code: str,
) -> RadarSnapshot:
    """Preserve a safe per-page fetch failure without retaining exception data."""

    if page_kind not in _ALLOWED_PAGE_KINDS:
        raise RadarSnapshotError("Radar page kind is not allowed")
    profile = session.get(CompetitorProfile, profile_id)
    run = session.get(RadarRun, run_id)
    if profile is None or run is None or run.profile_id != profile.id:
        raise RadarSnapshotError("Radar Run does not own this profile")
    content_hash = hashlib.sha256(f"unreachable:{canonical_url}:{reason_code}".encode()).hexdigest()
    existing = session.scalar(
        select(RadarSnapshot).where(
            RadarSnapshot.tenant_id == profile.tenant_id,
            RadarSnapshot.profile_id == profile.id,
            RadarSnapshot.canonical_url == canonical_url,
            RadarSnapshot.content_hash == content_hash,
        )
    )
    if existing is not None:
        return existing
    snapshot = RadarSnapshot(
        tenant_id=profile.tenant_id,
        profile_id=profile.id,
        run_id=run.id,
        page_kind=page_kind,
        requested_url=requested_url[:1000],
        canonical_url=canonical_url[:1000],
        content_hash=content_hash,
        facts_json=canonical_json({"facts": [], "reason_codes": [reason_code]}),
        excerpt="",
        source_method="static",
        validation_status="unreachable",
        extractor_version=RADAR_STATIC_EXTRACTOR_VERSION,
    )
    try:
        with session.begin_nested():
            session.add(snapshot)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(RadarSnapshot).where(
                RadarSnapshot.tenant_id == profile.tenant_id,
                RadarSnapshot.profile_id == profile.id,
                RadarSnapshot.canonical_url == canonical_url,
                RadarSnapshot.content_hash == content_hash,
            )
        )
        if existing is not None:
            return existing
        raise
    return snapshot


def _tracking_config(value: str) -> dict[str, Any]:
    try:
        config = parse_bounded_json_object(value)
    except RadarPolicyError as exc:
        raise RadarSnapshotError("Radar tracking configuration is invalid") from exc
    seed_pages = config.get("seed_pages", [])
    if not isinstance(seed_pages, list) or len(seed_pages) > 24:
        raise RadarSnapshotError("Radar seed page configuration is invalid")
    return config


def _same_domain_url(
    value: str,
    *,
    base_url: str,
    canonical_domain: str,
    resolver: Resolver,
    reject_foreign: bool,
) -> str | None:
    try:
        safe = canonical_public_url(urljoin(base_url, value.strip()), resolver=resolver)
    except UnsafeUrlError:
        if reject_foreign:
            raise RadarSnapshotError("Configured Radar page is not a public URL") from None
        return None
    if safe.host != canonical_domain:
        if reject_foreign:
            raise RadarSnapshotError("Radar page must use the same competitor domain")
        return None
    return safe.canonical_url


def _append_plan(
    planned: list[PlannedRadarPage],
    seen: set[str],
    canonical_url: str,
    page_kind: str,
    anchor_text: str,
) -> None:
    if canonical_url in seen:
        return
    seen.add(canonical_url)
    planned.append(
        PlannedRadarPage(
            requested_url=canonical_url,
            canonical_url=canonical_url,
            page_kind=page_kind,
            anchor_text=anchor_text[:200],
        )
    )


def _observed_link_values(value: object) -> tuple[str, str]:
    if isinstance(value, dict):
        url = value.get("url", "")
        anchor = value.get("anchor_text", "")
    elif isinstance(value, tuple) and len(value) == 2:
        url, anchor = value
    else:
        return "", ""
    return (
        url.strip() if isinstance(url, str) else "",
        anchor.strip() if isinstance(anchor, str) else "",
    )


def _classify_page(url: str, anchor_text: str) -> str:
    text = f"{url} {anchor_text}".casefold()
    for page_kind, markers in _PAGE_KIND_PATTERNS:
        if any(marker in text for marker in markers):
            return page_kind
    return "other"


def _structured_snapshot(fetched_page: FetchResult) -> tuple[str, str, str]:
    if fetched_page.detected_prompt_injection:
        return (
            canonical_json({"facts": [], "reason_codes": ["prompt_injection_detected"]}),
            "",
            "rejected",
        )
    normalized_text = " ".join(fetched_page.text.split())
    if _is_dynamic_shell(normalized_text):
        return (
            canonical_json({"facts": [], "reason_codes": ["requires_browser"]}),
            normalized_text[:4000],
            "partial",
        )
    excerpt = normalized_text[:4000]
    facts: list[dict[str, Any]] = []
    if fetched_page.title.strip():
        facts.append(
            {
                "extractor": RADAR_STATIC_EXTRACTOR_VERSION,
                "key": "page.title",
                "reason_codes": [],
                "source_url": fetched_page.final_url,
                "value": fetched_page.title.strip()[:500],
            }
        )
    if excerpt:
        facts.append(
            {
                "extractor": RADAR_STATIC_EXTRACTOR_VERSION,
                "key": "page.visible_text",
                "reason_codes": [],
                "source_url": fetched_page.final_url,
                "value": excerpt,
            }
        )
    return (
        canonical_json({"facts": facts, "reason_codes": ["no_relationships_observed"]}),
        excerpt,
        "valid",
    )


def _is_dynamic_shell(text: str) -> bool:
    lowered = text.casefold()
    return len(lowered.split()) <= 25 and any(
        marker in lowered for marker in _DYNAMIC_SHELL_MARKERS
    )
