"""
Client identity under the trusted-proxy boundary (app.core.client_ip).

Forwarding headers may only change the identity when the TCP peer is a
configured trusted proxy; everything else falls back to the real peer.
"""

import pytest
from starlette.requests import Request

from app.core import client_ip
from app.core.client_ip import ClientAddress, get_client_address

NEXT_PROXY = "10.0.0.5"


def _request(peer, headers=(), port=40000):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers],
        "client": (peer, port) if peer is not None else None,
    }
    return Request(scope)


@pytest.fixture
def trust(monkeypatch):
    settings = client_ip.get_settings()

    def _set(value):
        monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", value)

    _set("")
    return _set


def test_direct_request_ignores_spoofed_forwarded_for(trust):
    trust("")
    req = _request("198.51.100.20", [("X-Forwarded-For", "203.0.113.9")])
    assert get_client_address(req) == ClientAddress(ip="198.51.100.20")


def test_direct_request_ignores_spoof_even_when_other_proxies_are_trusted(trust):
    trust(NEXT_PROXY)
    req = _request("198.51.100.20", [("X-Forwarded-For", "203.0.113.9"), ("X-Real-IP", "203.0.113.10")])
    assert get_client_address(req).ip == "198.51.100.20"


def test_trusted_proxy_forwarded_client_is_used(trust):
    trust(NEXT_PROXY)
    req = _request(NEXT_PROXY, [("X-Forwarded-For", "203.0.113.9")])
    assert get_client_address(req) == ClientAddress(ip="203.0.113.9", forwarded=True)


def test_trusted_proxy_cidr(trust):
    trust("10.0.0.0/24, 192.168.65.0/24")
    req = _request("192.168.65.1", [("X-Forwarded-For", "203.0.113.9")])
    assert get_client_address(req).ip == "203.0.113.9"


def test_untrusted_proxy_headers_ignored(trust):
    trust(NEXT_PROXY)
    req = _request("10.0.0.99", [("X-Forwarded-For", "203.0.113.9")])
    # headers ignored; an internal address is infrastructure, so it is a shared identity
    assert get_client_address(req) == ClientAddress(ip="10.0.0.99", shared=True)
    req = _request("198.51.100.20", [("X-Forwarded-For", "203.0.113.9")])
    assert get_client_address(req) == ClientAddress(ip="198.51.100.20")


@pytest.mark.parametrize(
    "peer",
    ["127.0.0.1", "10.1.2.3", "172.24.0.1", "192.168.65.1", "100.64.0.9", "169.254.1.1", "::1", "fd00::5", "fe80::1"],
)
def test_unconfigured_internal_peer_is_shared_and_headers_ignored(trust, peer):
    # e.g. a Next.js server or load balancer nobody listed in TRUSTED_PROXY_IPS
    trust("")
    addr = get_client_address(_request(peer, [("X-Forwarded-For", "198.51.100.9")]))
    assert addr.shared is True
    assert addr.forwarded is False
    assert addr.ip == peer


@pytest.mark.parametrize("peer", ["198.51.100.20", "8.8.8.8", "2001:db8::1", "172.32.0.1", "100.128.0.1"])
def test_public_peer_is_an_individual_client(trust, peer):
    trust("")
    assert get_client_address(_request(peer)).shared is False


def test_internal_address_forwarded_by_trusted_proxy_is_shared(trust):
    trust(NEXT_PROXY)
    req = _request(NEXT_PROXY, [("X-Forwarded-For", "10.9.9.9")])
    assert get_client_address(req) == ClientAddress(ip="10.9.9.9", shared=True, forwarded=True)


def test_trusted_proxy_without_client_is_shared(trust):
    trust(NEXT_PROXY)
    assert get_client_address(_request(NEXT_PROXY)) == ClientAddress(ip=NEXT_PROXY, shared=True)


def test_multiple_values_take_rightmost_untrusted(trust):
    # attacker-chosen leftmost value is skipped; the edge proxy's view (rightmost untrusted) wins
    trust(f"{NEXT_PROXY},10.0.0.6")
    req = _request(NEXT_PROXY, [("X-Forwarded-For", "1.2.3.4, 203.0.113.9, 10.0.0.6")])
    assert get_client_address(req).ip == "203.0.113.9"


def test_repeated_headers_are_concatenated(trust):
    trust(NEXT_PROXY)
    req = _request(NEXT_PROXY, [("X-Forwarded-For", "1.2.3.4"), ("X-Forwarded-For", "203.0.113.9")])
    assert get_client_address(req).ip == "203.0.113.9"


def test_chain_of_only_trusted_hops_is_shared(trust):
    trust("10.0.0.0/8")
    req = _request(NEXT_PROXY, [("X-Forwarded-For", "10.1.1.1, 10.2.2.2")])
    assert get_client_address(req) == ClientAddress(ip=NEXT_PROXY, shared=True)


@pytest.mark.parametrize(
    "value",
    [
        "not-an-ip",
        "203.0.113.9:443",
        "[2001:db8::1]",
        "203.0.113.9, garbage",
        "203.0.113.9,,",
        "",
        "fe80::1%eth0",
        "999.1.1.1",
        ",".join(["203.0.113.9"] * 21),
    ],
)
def test_malformed_forwarded_for_falls_back_to_proxy(trust, value):
    trust(NEXT_PROXY)
    req = _request(NEXT_PROXY, [("X-Forwarded-For", value)])
    assert get_client_address(req) == ClientAddress(ip=NEXT_PROXY, shared=True)


def test_forwarded_and_real_ip_headers_never_trusted(trust):
    trust(NEXT_PROXY)
    req = _request(NEXT_PROXY, [("Forwarded", "for=203.0.113.9"), ("X-Real-IP", "203.0.113.10")])
    assert get_client_address(req) == ClientAddress(ip=NEXT_PROXY, shared=True)


def test_ipv4_identity(trust):
    addr = get_client_address(_request("198.51.100.20"))
    assert addr.ip == "198.51.100.20"
    assert addr.bucket == "198.51.100.20"


def test_ipv6_identity_grouped_by_64(trust):
    a = get_client_address(_request("2001:db8:aa:bb::1"))
    b = get_client_address(_request("2001:db8:aa:bb:ffff::2"))
    c = get_client_address(_request("2001:db8:aa:cc::1"))
    assert a.ip == "2001:db8:aa:bb::1"
    assert a.bucket == b.bucket == "2001:db8:aa:bb::/64"
    assert c.bucket != a.bucket


def test_ipv6_trusted_proxy_and_client(trust):
    trust("fd00::/8")
    req = _request("fd00::5", [("X-Forwarded-For", "2001:db8::9")])
    assert get_client_address(req) == ClientAddress(ip="2001:db8::9", forwarded=True)


def test_ipv4_mapped_ipv6_is_normalized(trust):
    trust(NEXT_PROXY)
    assert get_client_address(_request("::ffff:198.51.100.20")).ip == "198.51.100.20"
    req = _request(f"::ffff:{NEXT_PROXY}", [("X-Forwarded-For", "::ffff:203.0.113.9")])
    assert get_client_address(req).ip == "203.0.113.9"


def test_invalid_trusted_proxy_entries_do_not_widen_trust(trust):
    trust("not-a-network, *, 10.0.0.5")
    assert get_client_address(_request("198.51.100.20", [("X-Forwarded-For", "203.0.113.9")])).ip == "198.51.100.20"
    assert get_client_address(_request(NEXT_PROXY, [("X-Forwarded-For", "203.0.113.9")])).ip == "203.0.113.9"


def test_non_ip_peer_is_kept_and_headers_ignored(trust):
    trust("0.0.0.0/0")
    req = _request("testclient", [("X-Forwarded-For", "203.0.113.9")])
    assert get_client_address(req) == ClientAddress(ip="testclient")
    assert get_client_address(_request(None)).ip == "unknown"
