from __future__ import annotations

import re
from urllib.parse import urlsplit

DEFAULT_TAG_COLOR = "#246BFD"
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SAFE_URL_SCHEMES = {"http", "https"}


def safe_external_url(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in SAFE_URL_SCHEMES or not parsed.netloc:
        return ""
    return candidate


def safe_tag_color(value: str | None) -> str:
    candidate = (value or "").strip()
    if HEX_COLOR_RE.fullmatch(candidate):
        return candidate
    return DEFAULT_TAG_COLOR
