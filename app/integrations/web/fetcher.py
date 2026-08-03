"""Bounded, cookie-free static fetcher for public evidence pages."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx

from app.integrations.web.sanitizer import sanitize_html, sanitize_text
from app.integrations.web.url_safety import (
    Resolver,
    SafeUrl,
    UnsafeUrlError,
    system_resolver,
    validate_public_url,
)

_ALLOWED_CONTENT_TYPES = {"text/html", "text/plain", "application/xhtml+xml"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
DEFAULT_FETCH_MAX_BYTES = 1024 * 1024


class FetchError(RuntimeError):
    def __init__(self, code: str, safe_summary: str) -> None:
        super().__init__(f"{code}: {safe_summary}")
        self.code = code
        self.safe_summary = safe_summary


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    title: str
    text: str
    content_hash: str
    retrieved_at: datetime
    redirect_chain: tuple[str, ...]
    detected_prompt_injection: bool = False


class StaticFetcher:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
        max_bytes: int = DEFAULT_FETCH_MAX_BYTES,
        timeout_seconds: float = 10.0,
        max_redirects: int = 5,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.resolver = resolver
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.now = now or (lambda: datetime.now(UTC))
        self._closed = False
        self.client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            cookies=None,
            trust_env=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                "User-Agent": "LeadFlowEvidenceFetcher/1.0",
            },
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> StaticFetcher:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    @classmethod
    def from_app(cls, app) -> StaticFetcher:
        return cls(
            max_bytes=int(app.config.get("FETCH_MAX_BYTES", DEFAULT_FETCH_MAX_BYTES)),
            timeout_seconds=float(app.config.get("FETCH_TIMEOUT_SECONDS", 10)),
        )

    def fetch(self, url: str) -> FetchResult:
        requested_url = url
        safe = self._safe_url(url)
        redirect_chain: list[str] = []

        for redirect_count in range(self.max_redirects + 1):
            response_data = self._request(safe)
            status_code, headers, body = response_data
            self._verify_dns_unchanged(safe)

            if status_code in _REDIRECT_STATUSES:
                location = headers.get("location")
                if not location:
                    raise FetchError("invalid_redirect", "Redirect location is missing")
                if redirect_count >= self.max_redirects:
                    raise FetchError("too_many_redirects", "Redirect limit exceeded")
                redirect_chain.append(safe.canonical_url)
                safe = self._safe_url(urljoin(safe.canonical_url, location))
                continue

            if not 200 <= status_code < 300:
                raise FetchError("source_unreachable", "Evidence page request failed")

            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in _ALLOWED_CONTENT_TYPES:
                raise FetchError("unsupported_content_type", "Evidence page type is not supported")
            text = _decode_body(body, headers.get("content-type", ""))
            snapshot = sanitize_text(text) if content_type == "text/plain" else sanitize_html(text)
            content_hash = hashlib.sha256(snapshot.text.encode("utf-8")).hexdigest()
            return FetchResult(
                requested_url=requested_url,
                final_url=safe.canonical_url,
                status_code=status_code,
                content_type=content_type,
                title=snapshot.title,
                text=snapshot.text,
                content_hash=content_hash,
                retrieved_at=self.now(),
                redirect_chain=tuple(redirect_chain),
                detected_prompt_injection=snapshot.detected_prompt_injection,
            )

        raise FetchError("too_many_redirects", "Redirect limit exceeded")

    def _request(self, safe: SafeUrl) -> tuple[int, httpx.Headers, bytes]:
        try:
            with self.client.stream("GET", safe.canonical_url) as response:
                length = response.headers.get("content-length")
                if length and length.isdigit() and int(length) > self.max_bytes:
                    raise FetchError("response_too_large", "Evidence page exceeds size limit")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise FetchError("response_too_large", "Evidence page exceeds size limit")
                    chunks.append(chunk)
                return response.status_code, response.headers, b"".join(chunks)
        except FetchError:
            raise
        except httpx.TimeoutException:
            raise FetchError("source_timeout", "Evidence page request timed out") from None
        except httpx.HTTPError:
            raise FetchError("source_unreachable", "Evidence page request failed") from None

    def _safe_url(self, url: str) -> SafeUrl:
        try:
            return validate_public_url(url, resolver=self.resolver)
        except UnsafeUrlError:
            raise FetchError(
                "policy_url_blocked", "Evidence URL was blocked by safety policy"
            ) from None

    def _verify_dns_unchanged(self, before: SafeUrl) -> None:
        try:
            after = validate_public_url(before.canonical_url, resolver=self.resolver)
        except UnsafeUrlError:
            raise FetchError("dns_changed", "blocked DNS change after response") from None
        if after.resolved_ips != before.resolved_ips:
            raise FetchError("dns_changed", "blocked DNS change after response")


def _decode_body(body: bytes, content_type: str) -> str:
    encoding = "utf-8"
    for part in content_type.split(";")[1:]:
        name, separator, value = part.strip().partition("=")
        if separator and name.lower() == "charset" and value.strip():
            encoding = value.strip().strip("\"'")
            break
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")
