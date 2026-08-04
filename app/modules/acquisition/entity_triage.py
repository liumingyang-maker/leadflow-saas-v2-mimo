"""Small conservative pre-verification entity classifier."""

from __future__ import annotations

from urllib.parse import urlsplit

_MEDIA_MARKERS = ("/article", "/articles", "/blog", "/news", "/noticias", "/prensa", "/press")
_DIRECTORY_MARKERS = ("/directory", "/listing", "/marketplace", "/catalog", "/profile/")


def classify_discovery_entity(*, url: str, title: str, excerpt: str) -> str:
    """Return a non-company type only when URL semantics are explicit.

    Ambiguous company sites remain ``company`` so that this filter never acts
    as a broad, language-dependent rejector.
    """

    parsed = urlsplit(url)
    path = parsed.path.lower()
    host = (parsed.hostname or "").lower()
    combined = f"{title} {excerpt}".lower()
    if any(marker in path for marker in _DIRECTORY_MARKERS) or any(
        marker in host for marker in ("directory", "marketplace")
    ):
        return "directory_or_marketplace"
    if any(marker in path for marker in _MEDIA_MARKERS) or any(
        marker in host for marker in ("news", "press")
    ):
        return "media_or_article"
    if "business directory" in combined or "marketplace listing" in combined:
        return "directory_or_marketplace"
    return "company"
