from __future__ import annotations

import pytest


def test_proxy_rejects_private_or_mixed_dns_answers() -> None:
    from app.integrations.browser.egress_proxy import decide_connect

    assert decide_connect("example.com", 443, ("93.184.216.34",)).allowed is True
    assert decide_connect("example.com", 443, ("127.0.0.1",)).allowed is False
    assert decide_connect("example.com", 443, ("93.184.216.34", "10.0.0.4")).allowed is False


def test_proxy_rejects_plain_http_non_443_and_metadata() -> None:
    from app.integrations.browser.egress_proxy import decide_connect

    assert decide_connect("169.254.169.254", 443, ("169.254.169.254",)).allowed is False
    assert decide_connect("example.com", 80, ("93.184.216.34",)).reason == "port_blocked"


def test_connect_parser_rejects_non_connect_injection_and_oversized_headers() -> None:
    from app.integrations.browser.egress_proxy import ProxyProtocolError, parse_connect_request

    with pytest.raises(ProxyProtocolError, match="method_blocked"):
        parse_connect_request(b"GET http://example.com/ HTTP/1.1\r\n\r\n")
    with pytest.raises(ProxyProtocolError, match="authority_invalid"):
        parse_connect_request(b"CONNECT example.com:443@evil HTTP/1.1\r\n\r\n")
    with pytest.raises(ProxyProtocolError, match="header_too_large"):
        parse_connect_request(b"x" * (16 * 1024 + 1))


def test_resolver_runs_once_and_returns_pinned_numeric_address() -> None:
    from app.integrations.browser.egress_proxy import resolve_connect_target

    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    decision, address = resolve_connect_target("example.com", 443, resolver=resolver)
    assert decision.allowed is True
    assert address == "93.184.216.34"
    assert calls == ["example.com"]
