"""Client identity for rate limiting and login protection.

Trust boundary (the only place forwarding headers are interpreted):

- The TCP peer (``request.client``) is the starting point. Run uvicorn with
  ``--no-proxy-headers`` so the peer is the real socket address and uvicorn
  doesn't apply a second, different set of trust rules.
- ``X-Forwarded-For`` is read only when the peer is in ``TRUSTED_PROXY_IPS``
  (IPs/CIDRs, empty by default = trust nobody). The chain is walked right to
  left, skipping trusted hops; the first untrusted address is the client.
  Every entry must be a bare IPv4/IPv6 address, otherwise the header is ignored.
- ``Forwarded``, ``X-Real-IP`` and similar headers are never trusted.

The identity is ``shared`` (many users may sit behind it, so per-client
lockouts must not treat it as one client) when it is a trusted proxy that
didn't forward a usable client address, or an internal, non-routable address
(loopback, RFC 1918, CGNAT, link-local, IPv6 ULA). Internet clients can't
present such a source address, so an unconfigured Next.js server or load
balancer in front of the API fails safe instead of being locked out for everyone.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple, Union

from starlette.requests import Request

from app.core.config import get_settings

logger = logging.getLogger(__name__)

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]

MAX_FORWARDED_HOPS = 20
_warned_rewritten_peer = False

# Addresses of infrastructure, not of end users on the internet
INTERNAL_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


@dataclass(frozen=True)
class ClientAddress:
    """Who the request is from, as far as the trust boundary allows us to know."""

    ip: str  # normalized address, or the raw peer string if it isn't an IP (e.g. "testclient")
    shared: bool = False  # a trusted proxy that didn't tell us the end client
    forwarded: bool = False  # taken from X-Forwarded-For of a trusted proxy

    @property
    def bucket(self) -> str:
        """Key for per-client counters; IPv6 clients are grouped by /64 (one subscriber allocation)."""
        addr = parse_ip(self.ip)
        if isinstance(addr, ipaddress.IPv6Address):
            return str(ipaddress.IPv6Network((addr, 64), strict=False))
        return self.ip


def parse_ip(value: str) -> Optional[IPAddress]:
    """Strictly parse a bare IP address; IPv4-mapped IPv6 is unwrapped. None if malformed."""
    value = value.strip()
    if not value or len(value) > 45 or "%" in value:
        return None
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


@lru_cache(maxsize=8)
def parse_trusted_proxies(raw: str) -> Tuple[IPNetwork, ...]:
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            # Misconfiguration must not widen trust: skip the entry and say so
            logger.error("Ignoring invalid TRUSTED_PROXY_IPS entry: %r", item)
    return tuple(networks)


def _is_trusted(addr: IPAddress, trusted: Tuple[IPNetwork, ...]) -> bool:
    return any(addr.version == net.version and addr in net for net in trusted)


def _identity(addr: IPAddress, forwarded: bool = False) -> ClientAddress:
    return ClientAddress(ip=str(addr), shared=_is_trusted(addr, INTERNAL_NETWORKS), forwarded=forwarded)


def _forwarded_chain(request: Request) -> Optional[list[IPAddress]]:
    """All X-Forwarded-For entries (repeated headers concatenated), or None if absent/invalid."""
    values = request.headers.getlist("x-forwarded-for")
    if not values:
        return None
    entries = [part.strip() for value in values for part in value.split(",")]
    if not entries or len(entries) > MAX_FORWARDED_HOPS:
        return None
    chain = []
    for entry in entries:
        addr = parse_ip(entry)
        if addr is None:
            # Ambiguous or tampered chain: ignore it entirely rather than guess
            return None
        chain.append(addr)
    return chain


def get_client_address(request: Request) -> ClientAddress:
    """Resolve the client of ``request`` under the configured trust boundary."""
    global _warned_rewritten_peer

    client = request.client
    peer_raw = client.host if client and client.host else "unknown"
    if client and client.port == 0 and not _warned_rewritten_peer:
        # uvicorn's ProxyHeadersMiddleware already replaced the peer from X-Forwarded-For
        _warned_rewritten_peer = True
        logger.warning("Peer address was rewritten by the ASGI server; run uvicorn with --no-proxy-headers")

    peer = parse_ip(peer_raw)
    if peer is None:
        return ClientAddress(ip=peer_raw)

    trusted = parse_trusted_proxies(get_settings().TRUSTED_PROXY_IPS)
    if not trusted or not _is_trusted(peer, trusted):
        return _identity(peer)

    chain = _forwarded_chain(request)
    if chain:
        for addr in reversed(chain):
            if not _is_trusted(addr, trusted):
                return _identity(addr, forwarded=True)
    # Trusted proxy, but no usable end-client address
    return ClientAddress(ip=str(peer), shared=True)
