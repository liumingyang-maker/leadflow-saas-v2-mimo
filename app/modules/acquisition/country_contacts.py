"""Deterministic country and contact recovery from a fetched public page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.integrations.web.fetcher import FetchResult

_GENERIC_CCTLDS = {"ai", "cc", "co", "eu", "io", "me", "tv", "ws"}
_COUNTRY_ALIASES = {
    "AR": ("argentina",),
    "BR": ("brasil", "brazil"),
    "CL": ("chile",),
    "CO": ("colombia",),
    "ES": ("espana", "españa", "spain"),
    "MX": ("mexico", "méxico"),
    "PE": ("peru", "perú"),
    "US": ("united states", "usa", "u.s.a."),
}
_EMAIL_RE = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?){2,4}\d{2,4}(?!\w)")


@dataclass(frozen=True)
class DeterministicEvidence:
    country_code: str = ""
    country_confirmed: bool = False
    country_note: str = ""
    contact_paths: tuple[str, ...] = ()


def extract_deterministic_evidence(
    snapshot: FetchResult,
    *,
    target_country_code: str,
) -> DeterministicEvidence:
    domain_country = _domain_country(snapshot.final_url)
    target = target_country_code.strip().upper()
    text = snapshot.text.lower()
    aliases = _COUNTRY_ALIASES.get(target, ())
    page_names_target_country = bool(target and any(alias in text for alias in aliases))
    confirmed = bool(domain_country and domain_country == target and page_names_target_country)
    if confirmed:
        country_code = target
        country_note = f"confirmed:{target}:ccTLD+page_text"
    elif domain_country:
        country_code = domain_country
        country_note = f"likely:{domain_country}:ccTLD"
    else:
        country_code = ""
        country_note = ""
    return DeterministicEvidence(
        country_code=country_code,
        country_confirmed=confirmed,
        country_note=country_note,
        contact_paths=_contact_paths(snapshot),
    )


def merge_contact_paths(*path_sets: object) -> dict[str, object]:
    paths: list[str] = []
    for values in path_sets:
        if isinstance(values, dict):
            values = values.get("paths", [])
        if not isinstance(values, (list, tuple)):
            continue
        for value in values:
            path = str(value).strip()
            if path and path not in paths:
                paths.append(path)
    emails = [path.removeprefix("mailto:") for path in paths if path.startswith("mailto:")]
    return {"paths": paths[:20], "email": emails[0] if emails else ""}


def _domain_country(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    suffix = host.rsplit(".", 1)[-1]
    if len(suffix) != 2 or suffix in _GENERIC_CCTLDS:
        return ""
    return suffix.upper()


def _contact_paths(snapshot: FetchResult) -> tuple[str, ...]:
    paths: list[str] = []
    for email in _EMAIL_RE.findall(snapshot.text):
        path = f"mailto:{email.lower()}"
        if path not in paths:
            paths.append(path)
    for raw_phone in _PHONE_RE.findall(snapshot.text):
        digits = re.sub(r"\D", "", raw_phone)
        if 7 <= len(digits) <= 15:
            normalized = raw_phone.strip().replace(" ", "")
            path = f"tel:{normalized}"
            if path not in paths:
                paths.append(path)
    for url, label in snapshot.observed_links:
        lowered = f"{url} {label}".lower()
        if url.startswith(("mailto:", "tel:")) or any(
            marker in lowered for marker in ("contact", "contacto", "ventas", "sales")
        ):
            if url not in paths:
                paths.append(url)
    return tuple(paths[:20])
