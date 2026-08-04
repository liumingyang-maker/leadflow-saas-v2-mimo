"""Conservative source-to-company identity checks for public web evidence."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.integrations.web.fetcher import FetchResult

_GENERIC_NAME_TOKENS = {
    "and",
    "company",
    "corporacion",
    "corp",
    "del",
    "group",
    "importadora",
    "inc",
    "ltd",
    "peru",
    "sa",
    "sac",
    "srl",
    "the",
}


@dataclass(frozen=True)
class SourceIdentity:
    is_confirmed: bool
    source_type: str
    trust_tier: str
    validation_status: str


def classify_source_identity(company_name: str, snapshot: FetchResult) -> SourceIdentity:
    """Only call a page official when its domain is consistent with the company.

    This intentionally has no blacklist.  A third-party news domain can remain
    useful C-tier evidence, but it cannot inherit the A-tier official-site label.
    """

    host = (urlsplit(snapshot.final_url).hostname or "").lower().removeprefix("www.")
    normalized_host = _normalize(host.replace(".", " ").replace("-", " "))
    company_tokens = _company_tokens(company_name) or _company_tokens(snapshot.title)
    host_tokens = set(normalized_host.split())
    matched = any(
        token in host_tokens
        or token in normalized_host.replace(" ", "")
        or token.rstrip("s") in normalized_host.replace(" ", "")
        for token in company_tokens
    )
    if matched:
        return SourceIdentity(True, "official_website", "A", "valid")
    return SourceIdentity(False, "third_party_page", "C", "unverified")


def _company_tokens(value: str) -> set[str]:
    normalized = _normalize(value)
    return {
        token
        for token in normalized.split()
        if len(token) >= 4 and token not in _GENERIC_NAME_TOKENS
    }


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", folded.lower()))
