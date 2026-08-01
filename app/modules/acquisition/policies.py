from __future__ import annotations

import json

from app.modules.acquisition.contracts import MissionCreateInput

DEFAULT_EXCLUDE_TERMS = ["electric only", "marketplace", "supplier"]


def build_target_profile(value: MissionCreateInput) -> dict[str, object]:
    return {
        "country_codes": value.country_codes,
        "languages": value.languages,
        "buyer_types": value.buyer_types,
        "industries": value.industries,
        "company_sizes": value.company_sizes,
        "include_terms": value.include_terms,
        "exclude_terms": list(dict.fromkeys([*DEFAULT_EXCLUDE_TERMS, *value.exclude_terms])),
    }


def build_budget(value: MissionCreateInput) -> dict[str, int]:
    return {
        "max_candidates": value.max_candidates,
        "max_verify": value.max_verify,
        "max_search_actions": value.max_search_actions,
        "max_seconds": value.max_seconds,
    }


def build_channel_policy(value: MissionCreateInput) -> dict[str, object]:
    return {"allowed_channels": value.allowed_channels, "browser_research": False}


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
