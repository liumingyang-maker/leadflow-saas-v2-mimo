"""Deterministic, evidence-bound relationship proposals from Radar snapshots."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.web.url_safety import Resolver, UnsafeUrlError, system_resolver
from app.modules.radar.models import CompetitorProfile, RadarRelationship, RadarRun, RadarSnapshot
from app.modules.radar.policies import (
    canonical_json,
    canonical_public_url,
    parse_bounded_json_object,
)

RELATIONSHIP_DETECTOR_VERSION = "radar-relationships-v1"
_DIRECTORY_MARKERS = ("directory", "linkedin", "facebook", "instagram", "youtube", "google")
_TYPE_MARKERS = (
    ("distributor", ("distributor", "distribuidor", "分销")),
    ("dealer", ("dealer", "dealership", "经销")),
    ("service_network", ("service network", "service centre", "service center", "维修")),
    ("partner", ("partner", "partnership", "socio", "合作伙伴")),
)
_GENERIC_ANCHOR_MARKERS = (
    "read more",
    "read the",
    "learn more",
    "click here",
    "download",
    "view",
    "report",
)


class RadarRelationshipError(ValueError):
    """A stored snapshot cannot safely create a relationship proposal."""


def extract_relationships(
    session: Session,
    *,
    profile_id: str,
    run_id: str,
    snapshot_id: str,
    resolver: Resolver = system_resolver,
) -> tuple[RadarRelationship, ...]:
    """Create idempotent proposals using only one tenant-owned snapshot."""

    profile = session.get(CompetitorProfile, profile_id)
    run = session.get(RadarRun, run_id)
    snapshot = session.get(RadarSnapshot, snapshot_id)
    if (
        profile is None
        or run is None
        or snapshot is None
        or run.profile_id != profile.id
        or snapshot.profile_id != profile.id
        or snapshot.run_id != run.id
        or profile.tenant_id != run.tenant_id
        or snapshot.tenant_id != profile.tenant_id
        or snapshot.validation_status != "valid"
        or run.status == "cancelled"
    ):
        raise RadarRelationshipError("Radar snapshot is not eligible for relationship extraction")
    if not _is_official_competitor_source(snapshot, profile, resolver=resolver):
        return ()
    facts = parse_bounded_json_object(snapshot.facts_json)
    created: list[RadarRelationship] = []
    for target in _observed_targets(facts):
        proposal = _proposal_from_target(snapshot, profile, target, resolver=resolver)
        if proposal is None:
            continue
        existing = session.scalar(
            select(RadarRelationship).where(
                RadarRelationship.tenant_id == profile.tenant_id,
                RadarRelationship.profile_id == profile.id,
                RadarRelationship.canonical_domain == proposal["canonical_domain"],
                RadarRelationship.relationship_type == proposal["relationship_type"],
            )
        )
        if existing is not None:
            created.append(existing)
            continue
        relationship = RadarRelationship(
            tenant_id=profile.tenant_id,
            profile_id=profile.id,
            run_id=run.id,
            source_snapshot_id=snapshot.id,
            **proposal,
        )
        try:
            with session.begin_nested():
                session.add(relationship)
                session.flush()
        except IntegrityError:
            existing = session.scalar(
                select(RadarRelationship).where(
                    RadarRelationship.tenant_id == profile.tenant_id,
                    RadarRelationship.profile_id == profile.id,
                    RadarRelationship.canonical_domain == proposal["canonical_domain"],
                    RadarRelationship.relationship_type == proposal["relationship_type"],
                )
            )
            if existing is None:
                raise
            created.append(existing)
        else:
            created.append(relationship)
    return tuple(created)


def _is_official_competitor_source(
    snapshot: RadarSnapshot,
    profile: CompetitorProfile,
    *,
    resolver: Resolver,
) -> bool:
    try:
        source = canonical_public_url(snapshot.canonical_url, resolver=resolver)
        return source.host == profile.canonical_domain
    except UnsafeUrlError:
        return False


def _observed_targets(facts: dict[str, Any]) -> tuple[dict[str, str], ...]:
    rows = facts.get("facts", [])
    if not isinstance(rows, list):
        return ()
    targets: list[dict[str, str]] = []
    for row in rows[:50]:
        if not isinstance(row, dict) or row.get("key") != "page.observed_link":
            continue
        value = row.get("value")
        if not isinstance(value, dict):
            continue
        url = value.get("url")
        anchor_text = value.get("anchor_text")
        if isinstance(url, str) and isinstance(anchor_text, str):
            targets.append({"url": url[:1000], "anchor_text": anchor_text[:200]})
    return tuple(targets)


def _proposal_from_target(
    snapshot: RadarSnapshot,
    profile: CompetitorProfile,
    target: dict[str, str],
    *,
    resolver: Resolver,
) -> dict[str, str] | None:
    try:
        target_url = canonical_public_url(target["url"], resolver=resolver)
    except UnsafeUrlError:
        return None
    if target_url.host == profile.canonical_domain:
        return None
    company_name = " ".join(target["anchor_text"].split())[:300]
    if len(company_name) < 3:
        return None
    claim = _claim_for_target(snapshot.excerpt, company_name)
    relationship_type = _relationship_type(claim or "")
    reason_codes = ["official_source", "outbound_company_url", RELATIONSHIP_DETECTOR_VERSION]
    target_is_directory = any(marker in target_url.host for marker in _DIRECTORY_MARKERS)
    target_identity_unconfirmed = target_is_directory or _is_generic_anchor(company_name)
    if target_identity_unconfirmed:
        reason_codes.append("target_identity_unconfirmed")
    if (
        claim is not None
        and relationship_type in {"dealer", "distributor"}
        and not target_identity_unconfirmed
    ):
        strength = "confirmed"
        reason_codes.append("relationship_claim_confirmed")
    elif relationship_type == "unknown":
        strength = "unknown"
        reason_codes.append("relationship_claim_unresolved")
    else:
        strength = "likely"
        reason_codes.append("relationship_claim_likely")
    excerpt = _claim_excerpt(claim or snapshot.excerpt)
    return {
        "company_name": company_name,
        "canonical_domain": target_url.host,
        "official_url": target_url.canonical_url,
        "relationship_type": relationship_type,
        "evidence_strength": strength,
        "reason_codes_json": canonical_json(reason_codes),
        "evidence_json": canonical_json(
            [
                {
                    "excerpt": excerpt,
                    "outbound_url": target_url.canonical_url,
                    "source_url": snapshot.canonical_url,
                }
            ]
        ),
    }


def _relationship_type(excerpt: str) -> str:
    text = excerpt.casefold()
    for relation, markers in _TYPE_MARKERS:
        if any(marker in text for marker in markers):
            return relation
    return "unknown"


def _claim_for_target(excerpt: str, company_name: str) -> str | None:
    """Return the bounded sentence which names this outbound target and a relationship."""

    normalized_name = " ".join(company_name.casefold().split())
    if not normalized_name:
        return None
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", excerpt):
        normalized_sentence = " ".join(sentence.casefold().split())
        if (
            normalized_name in normalized_sentence
            and _relationship_type(normalized_sentence) != "unknown"
        ):
            return " ".join(sentence.split())[:1000]
    return None


def _is_generic_anchor(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return any(marker in normalized for marker in _GENERIC_ANCHOR_MARKERS)


def _claim_excerpt(value: str) -> str:
    return " ".join(value.split())[:1000]
