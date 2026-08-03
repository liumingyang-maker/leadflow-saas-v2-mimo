from __future__ import annotations

import json
from dataclasses import dataclass

from app.modules.radar.models import (
    CompetitorProfile,
    RadarChangeSignal,
    RadarCompetitorSuggestion,
    RadarRelationship,
    RadarRun,
    RadarSnapshot,
)
from app.modules.radar.policies import parse_bounded_json_object


@dataclass(frozen=True)
class RadarEvidenceView:
    source_url: str
    excerpt: str


@dataclass(frozen=True)
class RadarSuggestionView:
    id: str
    company_name: str
    canonical_domain: str
    official_url: str
    status: str
    reason_codes: tuple[str, ...]
    evidence: tuple[RadarEvidenceView, ...]


def suggestion_view(value: RadarCompetitorSuggestion) -> RadarSuggestionView:
    return RadarSuggestionView(
        id=value.id,
        company_name=value.company_name,
        canonical_domain=value.canonical_domain,
        official_url=value.official_url,
        status=value.status,
        reason_codes=_string_list(value.reason_codes_json, maximum=10, item_limit=80),
        evidence=_evidence_list(value.evidence_json),
    )


def profile_view(value: CompetitorProfile) -> dict[str, str]:
    return {
        "id": value.id,
        "company_name": value.company_name,
        "canonical_domain": value.canonical_domain,
        "official_url": value.official_url,
        "status": value.status,
        "mission_id": value.mission_id,
    }


def run_view(value: RadarRun) -> dict[str, object]:
    return {
        "id": value.id,
        "profile_id": value.profile_id,
        "status": value.status,
        "stage": value.stage,
        "budget": _safe_object(value.budget_json),
        "summary": _safe_object(value.result_summary_json),
        "created_at": value.created_at,
        "started_at": value.started_at,
        "finished_at": value.finished_at,
    }


def snapshot_view(value: RadarSnapshot) -> dict[str, object]:
    facts = _safe_object(value.facts_json)
    return {
        "id": value.id,
        "page_kind": value.page_kind,
        "requested_url": value.requested_url,
        "canonical_url": value.canonical_url,
        "source_method": value.source_method,
        "validation_status": value.validation_status,
        "reason_codes": _safe_strings(facts.get("reason_codes", []), maximum=10),
        "observed_at": value.observed_at,
    }


def relationship_view(value: RadarRelationship) -> dict[str, object]:
    evidence = _json_list(value.evidence_json)
    first = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
    return {
        "id": value.id,
        "company_name": value.company_name,
        "canonical_domain": value.canonical_domain,
        "official_url": value.official_url,
        "relationship_type": value.relationship_type,
        "evidence_strength": value.evidence_strength,
        "status": value.status,
        "candidate_id": value.candidate_id,
        "source_url": str(first.get("source_url", ""))[:1000],
        "excerpt": str(first.get("excerpt", ""))[:1000],
    }


def signal_view(value: RadarChangeSignal) -> dict[str, object]:
    return {
        "id": value.id,
        "change_type": value.change_type,
        "materiality": value.materiality,
        "status": value.status,
        "reason_codes": _string_list(value.reason_codes_json, maximum=10, item_limit=80),
    }


def _string_list(value: str, *, maximum: int, item_limit: int) -> tuple[str, ...]:
    parsed = _json_list(value)
    return tuple(item.strip()[:item_limit] for item in parsed[:maximum] if isinstance(item, str))


def _evidence_list(value: str) -> tuple[RadarEvidenceView, ...]:
    entries: list[RadarEvidenceView] = []
    for item in _json_list(value)[:2]:
        if not isinstance(item, dict):
            continue
        source_url = item.get("source_url")
        excerpt = item.get("excerpt")
        if isinstance(source_url, str) and isinstance(excerpt, str):
            entries.append(RadarEvidenceView(source_url=source_url[:1000], excerpt=excerpt[:1000]))
    return tuple(entries)


def _json_list(value: str) -> list[object]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_object(value: str) -> dict[str, object]:
    try:
        return parse_bounded_json_object(value)
    except ValueError:
        return {}


def _safe_strings(value: object, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item[:80] for item in value[:maximum] if isinstance(item, str))
