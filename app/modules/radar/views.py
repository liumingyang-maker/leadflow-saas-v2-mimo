from __future__ import annotations

import json
from dataclasses import dataclass

from app.modules.radar.models import CompetitorProfile, RadarCompetitorSuggestion


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
