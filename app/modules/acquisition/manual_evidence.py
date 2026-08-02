"""Deterministic validation for manually submitted company evidence."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import SplitResult, urlsplit

from app.integrations.ai.contracts import EvidenceClaim, ExtractedCompanyFacts
from app.integrations.web.fetcher import FetchResult
from app.modules.acquisition.contracts import ManualCompanyFactsInput

_EMAIL_PATTERN = re.compile(
    r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
    r"[A-Z]{2,63}",
    re.IGNORECASE | re.ASCII,
)
_PHONE_PATTERN = re.compile(r"[0-9+(). -]+")
_PHONE_SEPARATORS = frozenset("+() .-")
_EMAIL_TOKEN_CHARS = r"a-z0-9.!#$%&'*+/=?^_`{|}~@-"
_EMAIL_RIGHT_TOKEN_CHARS = r"a-z0-9!#$%&'*+/=?^_`{|}~@-"


class ManualEvidenceError(ValueError):
    """Raised when submitted evidence is not supported by fetched snapshots."""


def normalize_evidence_text(value: str) -> str:
    """Normalize text for deterministic, locale-safe substring matching."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def require_supported_text(*, claim: str, page_text: str) -> str:
    """Return readable claim text after proving it occurs in the page snapshot."""
    readable_claim = " ".join(claim.split())
    normalized_claim = normalize_evidence_text(readable_claim)
    if not normalized_claim or normalized_claim not in normalize_evidence_text(page_text):
        raise ManualEvidenceError("Evidence text is not supported by the fetched page")
    return readable_claim


def contact_url(value: str) -> str | None:
    """Return an HTTP(S) contact URL, or ``None`` for non-URL contact paths."""
    candidate = value.strip()
    if _safe_urlsplit(candidate).scheme.lower() in {"http", "https"}:
        return candidate
    return None


def normalise_domain(value: str) -> str:
    """Extract the normalized hostname used for strict same-domain comparisons."""
    candidate = value.strip()
    parsed = _safe_urlsplit(candidate if "://" in candidate else f"//{candidate}")
    hostname = parsed.hostname
    if not hostname:
        return ""
    clean = hostname.lower().rstrip(".")
    try:
        hostname = clean.encode("idna").decode("ascii")
    except UnicodeError:
        raise ManualEvidenceError("URL domain is malformed") from None
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def _safe_urlsplit(value: str) -> SplitResult:
    try:
        return urlsplit(value)
    except ValueError:
        raise ManualEvidenceError("URL is malformed") from None


def build_manual_company_facts(
    value: ManualCompanyFactsInput,
    *,
    primary: FetchResult,
    contact_snapshot: FetchResult | None,
) -> ExtractedCompanyFacts:
    """Build facts only from evidence proven against already-fetched snapshots."""
    evidence_text = require_supported_text(
        claim=value.evidence_text,
        page_text=primary.text,
    )
    canonical_domain = normalise_domain(primary.final_url)
    if not canonical_domain:
        raise ManualEvidenceError("Primary evidence URL has no valid domain")

    normalized_contact = _validate_contact_path(
        value.contact_path,
        canonical_domain=canonical_domain,
        primary=primary,
        contact_snapshot=contact_snapshot,
    )

    return ExtractedCompanyFacts(
        company_name=value.company_name,
        canonical_domain=canonical_domain,
        hq_country_code="",
        opportunity_country_code=value.opportunity_country_code,
        buyer_type=value.buyer_type,
        product_terms=[],
        contact_paths=[normalized_contact],
        observed_claims=[
            EvidenceClaim(
                claim_id="manual-product-evidence",
                text=evidence_text,
                source_url=primary.final_url,
            )
        ],
        inferences=[],
        unknowns=["hq_country_code"],
    )


def _validate_contact_path(
    value: str,
    *,
    canonical_domain: str,
    primary: FetchResult,
    contact_snapshot: FetchResult | None,
) -> str:
    submitted_url = contact_url(value)
    if submitted_url is not None:
        if normalise_domain(submitted_url) != canonical_domain:
            raise ManualEvidenceError("Contact URL must use the company domain")
        if contact_snapshot is None:
            raise ManualEvidenceError("Contact URL requires a fetched contact page")
        if contact_snapshot.requested_url != submitted_url:
            raise ManualEvidenceError("Contact snapshot does not match the submitted URL")
        if normalise_domain(contact_snapshot.final_url) != canonical_domain:
            raise ManualEvidenceError("Contact URL redirected off the company domain")
        return submitted_url

    normalized_contact, match_value = _normalise_non_url_contact(value)
    page_texts = [primary.text]
    if contact_snapshot is not None:
        page_texts.append(contact_snapshot.text)
    if not any(_contains_contact(match_value, page_text=text) for text in page_texts):
        raise ManualEvidenceError("Contact path is not supported by fetched evidence")
    return normalized_contact


def _normalise_non_url_contact(value: str) -> tuple[str, str]:
    candidate = " ".join(value.strip().split())
    if candidate.casefold().startswith("mailto:"):
        email = candidate[7:].strip()
        if _is_email(email):
            normalized_email = email.casefold()
            return f"mailto:{normalized_email}", normalized_email
    elif _is_email(candidate):
        normalized_email = candidate.casefold()
        return normalized_email, normalized_email
    elif (
        7 <= len(candidate) <= 25
        and _PHONE_PATTERN.fullmatch(candidate) is not None
        and sum(character.isdigit() for character in candidate) >= 7
    ):
        return candidate, candidate
    raise ManualEvidenceError("Contact path must be a supported email or phone")


def _contains_contact(value: str, *, page_text: str) -> bool:
    normalized_value = normalize_evidence_text(value)
    normalized_page = normalize_evidence_text(page_text)
    escaped_value = re.escape(normalized_value)
    if _is_email(normalized_value):
        pattern = (
            rf"(?<![{_EMAIL_TOKEN_CHARS}]){escaped_value}"
            rf"(?![{_EMAIL_RIGHT_TOKEN_CHARS}]|\.[a-z0-9])"
        )
        return re.search(pattern, normalized_page, flags=re.ASCII) is not None
    return _contains_standalone_phone(
        escaped_value=escaped_value,
        page_text=normalized_page,
    )


def _contains_standalone_phone(*, escaped_value: str, page_text: str) -> bool:
    for match in re.finditer(escaped_value, page_text, flags=re.ASCII):
        has_left_digit = _digit_beyond_phone_separators(
            page_text,
            index=match.start() - 1,
            step=-1,
        )
        has_right_digit = _digit_beyond_phone_separators(
            page_text,
            index=match.end(),
            step=1,
        )
        if not has_left_digit and not has_right_digit:
            return True
    return False


def _digit_beyond_phone_separators(text: str, *, index: int, step: int) -> bool:
    separator_characters: list[str] = []
    while 0 <= index < len(text) and text[index] in _PHONE_SEPARATORS:
        separator_characters.append(text[index])
        index += step
    if not (0 <= index < len(text) and text[index] in "0123456789"):
        return False
    if step < 0:
        separator_characters.reverse()
    separator_segment = "".join(separator_characters)
    return re.search(r"\.\s+", separator_segment) is None


def _is_email(value: str) -> bool:
    if len(value) > 254:
        return False
    local, separator, _domain = value.partition("@")
    return (
        bool(separator)
        and len(local) <= 64
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and _EMAIL_PATTERN.fullmatch(value) is not None
    )
