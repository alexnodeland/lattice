"""Egress: one policy for everything that calls out of the deployment, as pure functions.

Every outbound call has a :class:`Purpose`, such as ``litellm``, ``reader`` or
``connector:github``: the hosts the operator allows for it, and the internal destinations the
operator declares for it, each an exact host and port with the private range it must resolve
into. :func:`decide` says whether a :class:`Destination`, resolved, may be reached under a
purpose, given the hosts a tenant's and workspace's settings narrow it to and the caller's
taint, and answers a :class:`Verdict`: allowed, with the one checked address to connect to, so
DNS rebinding can't swap it; or refused, with the reason (lattice RFC-0011, lattice ADR-0033).

- **Metadata endpoints are always refused,** whatever the purpose or declaration
  (:data:`METADATA_HOSTS`, :data:`METADATA_NETWORKS`).
- **An internal destination** is reached only under its purpose, on its port, and only where
  every address it resolves to is inside its declared range. Only the operator declares one.
- **Any other host** must be among the purpose's hosts and those allowed where the call is made,
  and resolve only to public addresses: private, loopback, link-local, CGNAT and tailnet
  ranges, and the rest of :data:`REFUSED`, are refused on every address.
- **A tainted caller** reaches only hosts that appeared in what it read, and never with a URL
  built from private data, which the caller marks.

Envoy, the egress proxy, holds the operator's universe in its rendered configuration, and asks
an authorizer that runs :func:`decide` on every request; the reader's and the sandbox's guards
call it too, as defence in depth. Neither is declared here yet.

The contract's version is :data:`CONTRACT`, and its JSON Schema, which :func:`contract_schema`
returns, is checked in at ``schemas/egress.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import re
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from typing import Final, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyAddress,
    IPvAnyNetwork,
    JsonValue,
    model_validator,
)

from lattice_core.taint import Taint, Tainted

__all__ = [
    "CONTRACT",
    "HOST",
    "METADATA_HOSTS",
    "METADATA_NETWORKS",
    "PURPOSE",
    "REFUSED",
    "Destination",
    "InternalUpstream",
    "Purpose",
    "Verdict",
    "contract_schema",
    "decide",
    "host_matches",
    "metadata",
    "refused",
]

CONTRACT: Final = "1.0.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field is a minor one."""

PURPOSE: Final = re.compile(r"[a-z][a-z0-9-]*(:[a-z0-9][a-z0-9._-]*)?")
"""A purpose's key: a name, or a family, a colon and a name, such as ``litellm``,
``sandbox:registries``, ``connector:github`` or ``mcp:<server>``."""

HOST: Final = re.compile(
    r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)
"""A host's form: a DNS name in lowercase, without a trailing dot. A host pattern is one, or
``*.`` and one for any name below it."""

type Address = IPv4Address | IPv6Address
"""An IP address."""

type Network = IPv4Network | IPv6Network
"""An IP network."""

METADATA_HOSTS: Final = frozenset(
    {
        "metadata",
        "metadata.goog",
        "metadata.google.internal",
        "instance-data",
        "instance-data.ec2.internal",
    }
)
"""The names cloud metadata endpoints answer to, always refused."""

METADATA_NETWORKS: Final[tuple[Network, ...]] = tuple(
    ip_network(network)
    for network in (
        "169.254.169.254/32",  # AWS, GCP, Azure and others
        "169.254.170.2/32",  # AWS ECS task metadata and credentials
        "100.100.100.200/32",  # Alibaba Cloud
        "fd00:ec2::254/128",  # AWS over IPv6
    )
)
"""The addresses of cloud metadata endpoints, always refused, and never inside an internal
destination's range."""

REFUSED: Final[tuple[Network, ...]] = tuple(
    ip_network(network)
    for network in (
        "0.0.0.0/8",  # this network
        "10.0.0.0/8",  # private
        "100.64.0.0/10",  # CGNAT, and Tailscale's tailnet addresses
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local
        "172.16.0.0/12",  # private
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # documentation
        "192.88.99.0/24",  # 6to4 relay anycast
        "192.168.0.0/16",  # private
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # documentation
        "203.0.113.0/24",  # documentation
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved, and the broadcast address
        "::/128",  # unspecified
        "::1/128",  # loopback
        "::ffff:0:0/96",  # IPv4-mapped, refused whatever it maps to
        "64:ff9b::/96",  # NAT64, which reaches IPv4 behind it
        "64:ff9b:1::/48",  # local NAT64
        "100::/64",  # discard
        "2001::/32",  # Teredo, which tunnels to IPv4
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4, which tunnels to IPv4
        "fc00::/7",  # unique local, and Tailscale's tailnet addresses
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
)
"""The ranges refused on every resolved address, beyond any address Python's ``ipaddress``
doesn't call global. An internal destination's declared range is reached all the same."""


def metadata(address: Address) -> bool:
    """Whether an address is a cloud metadata endpoint's."""
    return any(address in network for network in METADATA_NETWORKS)


def refused(address: Address) -> bool:
    """Whether an address is refused for any host but an internal destination.

    It is refused if private, loopback, link-local, CGNAT, tailnet, multicast, reserved, or a
    tunnel to IPv4.
    """
    return (
        any(address in network for network in REFUSED)
        or not address.is_global
        or address.is_multicast
    )


def _host(value: str) -> str:
    """Return a host as it is compared: in lowercase, without a trailing dot."""
    return value.lower().removesuffix(".")


def host_matches(host: str, patterns: Iterable[str]) -> bool:
    """Whether a host is one of the patterns, or below one of the form ``*.<name>``."""
    host = _host(host)
    return any(
        host.endswith(pattern[1:]) if pattern.startswith("*.") else host == pattern
        for pattern in patterns
    )


def _pattern(pattern: str) -> str:
    if not HOST.fullmatch(pattern.removeprefix("*.")):
        raise ValueError(f"a host pattern is a lowercase name, or *. and one, not {pattern!r}")
    return pattern


class InternalUpstream(BaseModel):
    """A private destination the operator declares for a purpose, such as a self-hosted forge.

    It is reached only under its purpose, on its port, and only where every address its host
    resolves to is inside its range, still pinned against rebinding and narrowed by taint.

    Raises:
        ValueError: If the host isn't a lowercase name, or is a metadata endpoint's, or the
            range holds a metadata endpoint's address.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    host: str
    """Its host, exactly: ``forgejo.internal``."""
    port: int = Field(ge=1, le=65535)
    """Its port."""
    network: IPvAnyNetwork
    """The range its host must resolve into, such as ``10.0.4.0/24``."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not HOST.fullmatch(self.host):
            raise ValueError(f"an internal destination's host is a lowercase name: {self.host!r}")
        if self.host in METADATA_HOSTS or any(
            self.network.overlaps(network)
            for network in METADATA_NETWORKS
            if network.version == self.network.version
        ):
            raise ValueError(f"an internal destination is never a metadata endpoint: {self.host}")
        return self


class Purpose(BaseModel):
    """Why something calls out, and where the operator lets it reach.

    Raises:
        ValueError: If the key isn't of :data:`PURPOSE`'s form, a host pattern isn't a host or
            ``*.`` and one, or two internal destinations share a host and port.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    key: str
    """Its key: ``litellm``, ``reader``, ``sandbox:registries``, ``connector:github``."""
    hosts: frozenset[str] = frozenset()
    """The hosts it may reach, the operator's universe for it, which tenants and workspaces only
    narrow: names, or ``*.`` and a name for any name below it."""
    internal: tuple[InternalUpstream, ...] = ()
    """The private destinations the operator declares for it."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not PURPOSE.fullmatch(self.key):
            raise ValueError(f"a purpose's key is a name or family:name, not {self.key!r}")
        for pattern in self.hosts:
            _pattern(pattern)
        places = [(upstream.host, upstream.port) for upstream in self.internal]
        if len(set(places)) != len(places):
            raise ValueError(f"{self.key} declares an internal destination twice")
        return self


class Destination(BaseModel):
    """Where a call would go: its host and port, and every address the host resolved to.

    Raises:
        ValueError: If the host is empty.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    host: str
    """The host asked for, a name or an address."""
    port: int = Field(ge=1, le=65535)
    """The port asked for."""
    addresses: tuple[IPvAnyAddress, ...]
    """Every address the host resolved to, each checked."""
    private_data: bool = False
    """Whether the caller built the URL's path or query from private data, which a tainted
    caller may never send."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not self.host.strip():
            raise ValueError("a destination needs a host")
        return self


class Verdict(BaseModel):
    """Whether a call may go out, and to which checked address.

    Raises:
        ValueError: Unless an allowed verdict has an address and a refused one has none.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    allowed: bool
    """Whether the call may go out."""
    reason: str
    """Why, for the log and the caller: never the request's body or headers."""
    address: IPvAnyAddress | None = None
    """The checked address to connect to, and only it, if allowed."""
    internal: bool = False
    """Whether it is one of the purpose's internal destinations."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.allowed != (self.address is not None):
            raise ValueError("an allowed verdict has an address, and a refused one none")
        return self


def _refuse(reason: str) -> Verdict:
    return Verdict(allowed=False, reason=reason)


def decide(
    request: Destination, purpose: Purpose, allowed: Iterable[str], taint: Taint, /
) -> Verdict:
    """Decide whether a call may reach a destination under a purpose.

    Args:
        request: Where the call would go, resolved.
        purpose: The purpose it calls for, as the operator declares it.
        allowed: The host patterns allowed where the call is made: the purpose's hosts, as
            the tenant's and workspace's ``egress:<purpose>`` settings narrow them.
        taint: The caller's taint.
    """
    host = _host(request.host)
    addresses = request.addresses
    if host in METADATA_HOSTS or any(metadata(address) for address in addresses):
        return _refuse(f"{host} is a metadata endpoint")
    if not addresses:
        return _refuse(f"{host} resolved to no address")
    upstream = next((u for u in purpose.internal if (u.host, u.port) == (host, request.port)), None)
    if upstream is not None:
        if not all(address in upstream.network for address in addresses):
            return _refuse(f"{host} resolves outside the range declared for it")
    elif not host_matches(host, purpose.hosts):
        return _refuse(f"{host} isn't among {purpose.key}'s hosts")
    elif not host_matches(host, allowed):
        return _refuse(f"{host} isn't allowed for {purpose.key} here")
    elif any(refused(address) for address in addresses):
        return _refuse(f"{host} resolves to a private or reserved address")
    if isinstance(taint, Tainted):
        if host not in {_host(seen) for seen in taint.seen_hosts}:
            return _refuse(f"{host} wasn't seen in what this tainted caller read")
        if request.private_data:
            return _refuse("a tainted caller may not send a URL built from private data")
    return Verdict(
        allowed=True,
        reason="internal destination" if upstream is not None else "allowed",
        address=addresses[0],
        internal=upstream is not None,
    )


class _Contract(BaseModel):
    purpose: Purpose
    destination: Destination
    verdict: Verdict


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: a purpose, a destination and a verdict."""
    schema = _Contract.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.egress {CONTRACT}",
        "description": (
            "lattice's egress contract: `purpose` is why something calls out and where the "
            "operator lets it, `destination` where a call would go, resolved, and `verdict` "
            "whether it may, and to which checked address."
        ),
        "type": "object",
        "properties": schema["properties"],
        "$defs": schema["$defs"],
    }
