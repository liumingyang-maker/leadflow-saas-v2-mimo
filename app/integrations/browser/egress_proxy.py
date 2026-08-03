"""A small CONNECT-only proxy for the isolated Browser container."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

MAX_HEADER_BYTES = 16 * 1024
MAX_HOST_BYTES = 253
BUFFER_BYTES = 64 * 1024
IDLE_TIMEOUT_SECONDS = 45
TOTAL_TIMEOUT_SECONDS = 300

Resolver = Callable[[str], list[str] | tuple[str, ...]]
logger = logging.getLogger(__name__)


class ProxyProtocolError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ConnectDecision:
    allowed: bool
    reason: str


def _is_public_ip(value: str) -> bool:
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


def decide_connect(host: str, port: int, resolved_ips: tuple[str, ...]) -> ConnectDecision:
    """Check a single, already-resolved CONNECT request without network I/O."""

    if port != 443:
        return ConnectDecision(False, "port_blocked")
    if not host or len(host.encode("utf-8")) > MAX_HOST_BYTES:
        return ConnectDecision(False, "host_invalid")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return ConnectDecision(False, "ip_literal_blocked")
    if not resolved_ips:
        return ConnectDecision(False, "dns_unresolved")
    if any(not _is_public_ip(value) for value in resolved_ips):
        return ConnectDecision(False, "non_public_dns")
    return ConnectDecision(True, "allowed")


def parse_connect_request(header_block: bytes) -> tuple[str, int]:
    if len(header_block) > MAX_HEADER_BYTES:
        raise ProxyProtocolError("header_too_large")
    if not header_block.endswith(b"\r\n\r\n"):
        raise ProxyProtocolError("header_incomplete")
    try:
        lines = header_block[:-4].decode("ascii", errors="strict").split("\r\n")
    except UnicodeDecodeError as exc:
        raise ProxyProtocolError("header_invalid") from exc
    if not lines or not lines[0]:
        raise ProxyProtocolError("request_invalid")
    request_parts = lines[0].split(" ")
    if len(request_parts) != 3:
        raise ProxyProtocolError("request_invalid")
    method, authority, version = request_parts
    if method != "CONNECT":
        raise ProxyProtocolError("method_blocked")
    if version != "HTTP/1.1":
        raise ProxyProtocolError("version_blocked")
    for line in lines[1:]:
        if not line or ":" not in line:
            raise ProxyProtocolError("header_invalid")
        name, _value = line.split(":", 1)
        if name.strip().lower() in {"authorization", "proxy-authorization"}:
            raise ProxyProtocolError("authentication_blocked")
    if authority.count(":") != 1 or any(char in authority for char in "@/\\[]?#"):
        raise ProxyProtocolError("authority_invalid")
    host, raw_port = authority.rsplit(":", 1)
    if not host or not raw_port.isascii() or not raw_port.isdecimal():
        raise ProxyProtocolError("authority_invalid")
    try:
        canonical_host = host.rstrip(".").lower().encode("idna").decode("ascii")
        port = int(raw_port)
    except (UnicodeError, ValueError) as exc:
        raise ProxyProtocolError("authority_invalid") from exc
    if len(canonical_host) > MAX_HOST_BYTES:
        raise ProxyProtocolError("authority_invalid")
    return canonical_host, port


def system_resolver(host: str) -> list[str]:
    return sorted({item[4][0] for item in socket.getaddrinfo(host, None)})


def resolve_connect_target(
    host: str, port: int, *, resolver: Resolver = system_resolver
) -> tuple[ConnectDecision, str | None]:
    """Resolve once, validate all answers, then select a pinned numeric address."""

    try:
        answers = tuple(sorted(set(resolver(host))))
    except (OSError, RuntimeError, StopIteration, TypeError, ValueError):
        return ConnectDecision(False, "dns_unresolved"), None
    decision = decide_connect(host, port, answers)
    return decision, answers[0] if decision.allowed else None


def _host_digest(host: str) -> str:
    return hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]


def _log(
    request_id: str,
    host: str,
    reason: str,
    *,
    started: float,
    bytes_in: int = 0,
    bytes_out: int = 0,
) -> None:
    logger.info(
        "browser_egress request_id=%s host_hash=%s reason=%s "
        "bytes_in=%s bytes_out=%s duration_ms=%s",
        request_id,
        _host_digest(host),
        reason,
        bytes_in,
        bytes_out,
        int((time.monotonic() - started) * 1000),
    )


async def _copy(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, counter: list[int]
) -> None:
    while True:
        chunk = await asyncio.wait_for(reader.read(BUFFER_BYTES), timeout=IDLE_TIMEOUT_SECONDS)
        if not chunk:
            try:
                writer.write_eof()
            except (AttributeError, OSError):
                pass
            return
        counter[0] += len(chunk)
        writer.write(chunk)
        await writer.drain()


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    resolver: Resolver = system_resolver,
) -> None:
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    host = ""
    inbound = [0]
    outbound = [0]
    tunnel_open = False
    remote_writer: asyncio.StreamWriter | None = None
    try:
        try:
            header = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=IDLE_TIMEOUT_SECONDS
            )
        except asyncio.LimitOverrunError as exc:
            raise ProxyProtocolError("header_too_large") from exc
        host, port = parse_connect_request(header)
        decision, address = resolve_connect_target(host, port, resolver=resolver)
        if not decision.allowed or address is None:
            raise ProxyProtocolError(decision.reason)
        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(address, port), timeout=IDLE_TIMEOUT_SECONDS
        )
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        tunnel_open = True
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            await asyncio.gather(
                _copy(reader, remote_writer, inbound),
                _copy(remote_reader, writer, outbound),
            )
        _log(
            request_id, host, "closed", started=started, bytes_in=inbound[0], bytes_out=outbound[0]
        )
    except (TimeoutError, ProxyProtocolError, OSError) as exc:
        code = exc.code if isinstance(exc, ProxyProtocolError) else "connection_failed"
        if not tunnel_open:
            writer.write(f"HTTP/1.1 403 {code}\r\nConnection: close\r\n\r\n".encode("ascii"))
            try:
                await writer.drain()
            except (ConnectionError, OSError):
                pass
        _log(request_id, host, code, started=started, bytes_in=inbound[0], bytes_out=outbound[0])
    finally:
        if remote_writer is not None:
            remote_writer.close()
            try:
                await remote_writer.wait_closed()
            except OSError:
                pass
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def serve(*, host: str = "0.0.0.0", port: int = 8080) -> None:
    server = await asyncio.start_server(handle_client, host=host, port=port, limit=MAX_HEADER_BYTES)
    async with server:
        await server.serve_forever()
