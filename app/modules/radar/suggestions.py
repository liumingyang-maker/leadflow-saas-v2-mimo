from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.integrations.ai.contracts import CompetitorSuggestionResults
from app.integrations.web.url_safety import Resolver, UnsafeUrlError, system_resolver
from app.modules.radar.policies import canonical_json, canonical_public_url, evidence_hash


class RadarProposalError(ValueError):
    """A provider proposal cannot be stored as human-reviewable Radar evidence."""


@dataclass(frozen=True)
class ValidatedCompetitorSuggestion:
    company_name: str
    canonical_domain: str
    official_url: str
    reason_codes_json: str
    evidence_json: str
    evidence_hash: str


def validate_competitor_suggestions(
    proposal: object,
    *,
    product_summary: str,
    resolver: Resolver = system_resolver,
) -> tuple[ValidatedCompetitorSuggestion, ...]:
    """Validate the provider boundary again before tenant data is persisted."""

    try:
        raw: Any = proposal.model_dump(mode="json") if isinstance(proposal, BaseModel) else proposal
        results = CompetitorSuggestionResults.model_validate(raw)
    except (ValidationError, TypeError, ValueError) as exc:
        raise RadarProposalError("Competitor suggestions failed schema validation") from exc

    validated: list[ValidatedCompetitorSuggestion] = []
    seen_domains: set[str] = set()
    for suggestion in results.suggestions:
        try:
            official = canonical_public_url(str(suggestion.official_url), resolver=resolver)
            evidence = [
                {
                    "source_url": canonical_public_url(
                        str(item.source_url), resolver=resolver
                    ).canonical_url,
                    "excerpt": item.excerpt.strip(),
                }
                for item in suggestion.evidence
            ]
        except UnsafeUrlError as exc:
            raise RadarProposalError("Competitor suggestion contains an unsafe URL") from exc
        if official.host in seen_domains:
            raise RadarProposalError("Competitor suggestions repeat a canonical domain")
        if not _evidence_supports_competitor_relevance(
            suggestion.company_name,
            product_summary,
            evidence,
        ):
            raise RadarProposalError("Competitor evidence does not support mission relevance")
        seen_domains.add(official.host)
        evidence_json = canonical_json(evidence)
        validated.append(
            ValidatedCompetitorSuggestion(
                company_name=suggestion.company_name.strip(),
                canonical_domain=official.host,
                official_url=official.canonical_url,
                reason_codes_json=canonical_json(
                    [item.strip() for item in suggestion.reason_codes]
                ),
                evidence_json=evidence_json,
                evidence_hash=evidence_hash(evidence),
            )
        )
    return tuple(validated)


def _evidence_supports_competitor_relevance(
    company_name: str,
    product_summary: str,
    evidence: list[dict[str, str]],
) -> bool:
    company_marker = _normalized_text(company_name)
    product_terms = _significant_terms(product_summary)
    if not company_marker or not product_terms:
        return False
    for item in evidence:
        excerpt = _normalized_text(item["excerpt"])
        if company_marker not in excerpt:
            continue
        if product_terms.intersection(_significant_terms(excerpt)):
            return True
    return False


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _significant_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for raw in re.findall(r"\w+", value.casefold(), flags=re.UNICODE):
        normalized = raw[:-1] if raw.isascii() and raw.endswith("s") and len(raw) > 4 else raw
        if len(normalized) >= 3:
            terms.add(normalized)
    return terms
