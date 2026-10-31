"""Egress: one policy, as pure functions: metadata always refused, internal destinations only as
declared, private ranges refused on every address, hosts as the operator and the tenant allow
them, and a tainted caller narrowed (lattice RFC-0011, lattice ADR-0033)."""

from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from typing import Any

import pytest
from pydantic import ValidationError

from lattice_core.egress import (
    CONTRACT,
    METADATA_HOSTS,
    Destination,
    InternalUpstream,
    Purpose,
    Verdict,
    contract_schema,
    decide,
    host_matches,
    metadata,
    refused,
)
from lattice_core.taint import Cause, Clean, Tainted

FORGEJO = InternalUpstream(host="forgejo.internal", port=3000, network=ip_network("10.0.4.0/24"))
CONNECTOR = Purpose(
    key="connector:github",
    hosts=frozenset({"api.github.com", "*.githubusercontent.com"}),
)
FORGE = Purpose(key="forge:conn-1", hosts=frozenset({"codeberg.org"}), internal=(FORGEJO,))
PUBLIC = "140.82.112.6"
TAINTED = Tainted(
    causes=(Cause(capability="reader.read_page", at=datetime(2026, 10, 31, tzinfo=UTC)),),
    seen_hosts=frozenset({"API.GitHub.com."}),
)


def to(host: str, *addresses: str, port: int = 443, **changes: Any) -> Destination:
    fields: dict[str, Any] = {
        "host": host,
        "port": port,
        "addresses": tuple(ip_address(address) for address in addresses),
    }
    return Destination.model_validate(fields | changes)


def verdict(
    request: Destination,
    purpose: Purpose = CONNECTOR,
    allowed: frozenset[str] | None = None,
    taint: Clean | Tainted | None = None,
) -> Verdict:
    return decide(request, purpose, purpose.hosts if allowed is None else allowed, taint or Clean())


# ─── The pieces ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("host", "matches"),
    [
        ("api.github.com", True),
        ("API.GitHub.com.", True),
        ("raw.githubusercontent.com", True),
        ("a.b.githubusercontent.com", True),
        ("githubusercontent.com", False),
        ("evilgithubusercontent.com", False),
        ("github.com", False),
        ("api.github.com.evil.example", False),
    ],
)
def test_a_host_matches_a_name_exactly_or_a_wildcard_below_it(host: str, matches: bool) -> None:
    assert host_matches(host, CONNECTOR.hosts) is matches


@pytest.mark.parametrize(
    ("address", "is_refused"),
    [
        ("10.1.2.3", True),
        ("172.16.0.1", True),
        ("192.168.1.1", True),
        ("127.0.0.1", True),
        ("0.0.0.0", True),
        ("169.254.1.1", True),
        ("100.64.0.1", True),
        ("100.101.102.103", True),
        ("198.18.0.1", True),
        ("224.0.1.1", True),
        ("255.255.255.255", True),
        ("::1", True),
        ("::", True),
        ("fe80::1", True),
        ("fd7a:115c:a1e0::1", True),
        ("::ffff:8.8.8.8", True),
        ("::ffff:10.0.0.1", True),
        ("64:ff9b::a00:1", True),
        ("2002:a00:1::", True),
        ("2001:0:4136:e378::1", True),
        ("2001:db8::1", True),
        ("ff02::1", True),
        (PUBLIC, False),
        ("8.8.8.8", False),
        ("2606:4700:4700::1111", False),
    ],
)
def test_private_reserved_and_tunnelled_addresses_are_refused(
    address: str, is_refused: bool
) -> None:
    assert refused(ip_address(address)) is is_refused


@pytest.mark.parametrize(
    ("address", "is_metadata"),
    [
        ("169.254.169.254", True),
        ("169.254.170.2", True),
        ("100.100.100.200", True),
        ("fd00:ec2::254", True),
        ("169.254.169.253", False),
        ("::a9fe:a9fe", False),
    ],
)
def test_metadata_endpoints_are_known_by_address(address: str, is_metadata: bool) -> None:
    assert metadata(ip_address(address)) is is_metadata


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"host": "Forgejo.internal", "port": 3000, "network": "10.0.4.0/24"}, "lowercase"),
        ({"host": "metadata.google.internal", "port": 80, "network": "10.0.4.0/24"}, "metadata"),
        ({"host": "imds.internal", "port": 80, "network": "169.254.0.0/16"}, "metadata"),
        ({"host": "imds.internal", "port": 80, "network": "fd00:ec2::/64"}, "metadata"),
        ({"host": "forgejo.internal", "port": 0, "network": "10.0.4.0/24"}, "greater than"),
    ],
)
def test_an_internal_destination_is_never_a_metadata_endpoint(
    fields: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValidationError, match=says):
        InternalUpstream.model_validate(fields)


def test_an_internal_destination_over_ipv6_is_declared_by_its_range() -> None:
    assert InternalUpstream(host="litellm.internal", port=4000, network=ip_network("fd12::/64"))


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"key": "Connector"}, "name or family:name"),
        ({"key": "reader", "hosts": frozenset({"*"})}, "host pattern"),
        ({"key": "reader", "hosts": frozenset({"Example.com"})}, "host pattern"),
        ({"key": "reader", "hosts": frozenset({"a.*.example.com"})}, "host pattern"),
        ({"key": "forge:x", "internal": (FORGEJO, FORGEJO)}, "twice"),
    ],
)
def test_a_purpose_is_refused_when_malformed(fields: dict[str, Any], says: str) -> None:
    with pytest.raises(ValidationError, match=says):
        Purpose.model_validate(fields)


def test_a_destination_needs_a_host() -> None:
    with pytest.raises(ValidationError, match="needs a host"):
        to(" ", PUBLIC)


@pytest.mark.parametrize("fields", [{"allowed": True}, {"allowed": False, "address": PUBLIC}])
def test_a_verdict_has_an_address_exactly_when_allowed(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="address"):
        Verdict.model_validate({"reason": "why"} | fields)


# ─── decide ───────────────────────────────────────────────────────────────────


def test_an_allowed_host_resolving_to_public_addresses_is_reached_at_the_first() -> None:
    allowed = verdict(to("api.github.com", PUBLIC, "140.82.112.7"))
    assert allowed == Verdict(allowed=True, reason="allowed", address=ip_address(PUBLIC))


@pytest.mark.parametrize("host", sorted(METADATA_HOSTS))
def test_a_metadata_name_is_refused_whatever_it_resolves_to(host: str) -> None:
    purpose = Purpose(key="reader", hosts=frozenset({host}))
    assert not verdict(to(host, PUBLIC), purpose).allowed


@pytest.mark.parametrize("address", ["169.254.169.254", "fd00:ec2::254", "169.254.170.2"])
def test_a_metadata_address_is_refused_even_among_public_ones(address: str) -> None:
    refusal = verdict(to("api.github.com", PUBLIC, address))
    assert (refusal.allowed, refusal.reason) == (False, "api.github.com is a metadata endpoint")


def test_a_host_that_resolved_to_nothing_is_refused() -> None:
    assert verdict(to("api.github.com")).reason == "api.github.com resolved to no address"


def test_a_host_outside_the_purpose_is_refused() -> None:
    assert (
        verdict(to("example.com", PUBLIC)).reason
        == "example.com isn't among connector:github's hosts"
    )


def test_a_host_the_tenant_narrowed_away_is_refused() -> None:
    narrowed = frozenset({"*.githubusercontent.com"})
    refusal = verdict(to("api.github.com", PUBLIC), allowed=narrowed)
    assert refusal.reason == "api.github.com isn't allowed for connector:github here"
    assert verdict(to("raw.githubusercontent.com", PUBLIC), allowed=narrowed).allowed


@pytest.mark.parametrize(
    "address", ["10.0.0.5", "127.0.0.1", "100.100.1.1", "::1", "fd7a:115c:a1e0::5"]
)
def test_an_allowed_host_resolving_to_any_private_address_is_refused(address: str) -> None:
    refusal = verdict(to("api.github.com", PUBLIC, address))
    assert refusal.reason == "api.github.com resolves to a private or reserved address"


def test_an_internal_destination_is_reached_only_inside_its_range_and_on_its_port() -> None:
    reached = verdict(to("forgejo.internal", "10.0.4.20", port=3000), FORGE)
    assert reached == Verdict(
        allowed=True, reason="internal destination", address=ip_address("10.0.4.20"), internal=True
    )
    rebound = verdict(to("forgejo.internal", "10.0.4.20", "10.0.9.1", port=3000), FORGE)
    assert rebound.reason == "forgejo.internal resolves outside the range declared for it"
    assert not verdict(to("forgejo.internal", "fd00::1", port=3000), FORGE).allowed
    other_port = verdict(to("forgejo.internal", "10.0.4.20", port=22), FORGE)
    assert other_port.reason == "forgejo.internal isn't among forge:conn-1's hosts"


def test_an_internal_destination_is_reached_under_its_purpose_alone() -> None:
    elsewhere = Purpose(key="reader", hosts=frozenset({"forgejo.internal"}))
    refusal = verdict(to("forgejo.internal", "10.0.4.20", port=3000), elsewhere)
    assert refusal.reason == "forgejo.internal resolves to a private or reserved address"


def test_a_tainted_caller_reaches_only_hosts_it_has_seen() -> None:
    seen = verdict(to("api.github.com", PUBLIC), taint=TAINTED)
    assert seen.allowed
    unseen = verdict(to("raw.githubusercontent.com", PUBLIC), taint=TAINTED)
    assert unseen.reason == "raw.githubusercontent.com wasn't seen in what this tainted caller read"
    internal = verdict(to("forgejo.internal", "10.0.4.20", port=3000), FORGE, taint=TAINTED)
    assert not internal.allowed


def test_a_tainted_caller_never_sends_a_url_built_from_private_data() -> None:
    leaking = to("api.github.com", PUBLIC, private_data=True)
    assert verdict(leaking).allowed
    refusal = verdict(leaking, taint=TAINTED)
    assert refusal.reason == "a tainted caller may not send a URL built from private data"


# ─── The contract ─────────────────────────────────────────────────────────────


def test_the_contracts_schema_names_its_version_and_holds_its_three_parts() -> None:
    schema = contract_schema()
    assert schema["title"] == f"lattice.egress {CONTRACT}"
    assert schema["properties"] == {
        "purpose": {"$ref": "#/$defs/Purpose"},
        "destination": {"$ref": "#/$defs/Destination"},
        "verdict": {"$ref": "#/$defs/Verdict"},
    }
