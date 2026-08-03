"""SSRF-resistant URL parsing and public address validation."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class UnsafeUrlError(ValueError):
    pass


@dataclass(frozen=True)
class SafeUrl:
    canonical_url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]

    @property
    def origin(self) -> str:
        return f"https://{self.host}" if self.port == 443 else f"http://{self.host}"


Resolver = Callable[[str], list[str]]


def system_resolver(host: str) -> list[str]:
    return sorted({item[4][0] for item in socket.getaddrinfo(host, None)})


def _is_public(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _ascii_host(host: str) -> str:
    clean = host.rstrip(".").lower()
    try:
        ipaddress.ip_address(clean)
        return clean
    except ValueError:
        pass
    try:
        return clean.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeUrlError("blocked invalid host") from exc


def _blocked_hostname(host: str) -> bool:
    return (
        host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
        or host.endswith(".internal")
        or host == "metadata.google.internal"
    )


def validate_public_url(url: str, *, resolver: Resolver = system_resolver) -> SafeUrl:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except (TypeError, ValueError) as exc:
        raise UnsafeUrlError("blocked invalid URL") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("blocked invalid scheme or host")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("blocked embedded credentials")
    if port not in {80, 443}:
        raise UnsafeUrlError("blocked non-standard port")

    host = _ascii_host(parsed.hostname)
    if _blocked_hostname(host):
        raise UnsafeUrlError("blocked local or metadata host")
    try:
        addresses = tuple(sorted(set(resolver(host))))
    except (OSError, RuntimeError, StopIteration) as exc:
        raise UnsafeUrlError("blocked unresolved host") from exc
    if not addresses or any(not _is_public(address) for address in addresses):
        raise UnsafeUrlError("blocked non-public address")

    host_for_url = f"[{host}]" if ":" in host else host
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = host_for_url if default_port else f"{host_for_url}:{port}"
    canonical = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return SafeUrl(canonical, host, port, addresses)


def validate_browser_public_url(url: str, *, resolver: Resolver = system_resolver) -> SafeUrl:
    """Resolve a Browser navigation URL under the stricter HTTPS-only policy."""

    try:
        parsed = urlsplit(url.strip())
    except (TypeError, ValueError) as exc:
        raise UnsafeUrlError("blocked invalid URL") from exc
    if parsed.scheme.lower() != "https" or parsed.port not in {None, 443}:
        raise UnsafeUrlError("blocked Browser URL scheme or port")
    # Fragments do not affect network navigation but can carry secrets into artifacts/logs.
    if parsed.fragment:
        raise UnsafeUrlError("blocked Browser URL fragment")
    return validate_public_url(url, resolver=resolver)
