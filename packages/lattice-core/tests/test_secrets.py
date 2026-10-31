"""Secrets: references everywhere, values read only within their owner and purpose, rotated with
a grace period, revoked at once and deleted with their owner (lattice RFC-0011)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from lattice_core.secrets import (
    CONTRACT,
    FakeRead,
    FakeSecrets,
    OutOfScope,
    Owner,
    Reader,
    Revoked,
    SecretRef,
    Secrets,
    SecretVersion,
    UnknownSecret,
    VersionGone,
    contract_schema,
)

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)
ACME = Owner(tenant_id="acme")
DOCS = Owner(tenant_id="acme", workspace_id="docs")
GITHUB = Owner(tenant_id="acme", workspace_id="docs", connection_id="conn_gh")


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def reader(scope: Owner = GITHUB, purpose: str = "forge:token", **changes: Any) -> Reader:
    fields: dict[str, Any] = {"component": "credential-proxy", "scope": scope, "purpose": purpose}
    return Reader.model_validate(fields | changes)


def value(text: str = "ghp_first") -> SecretStr:
    return SecretStr(text)


# ─── The types ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("owner", "other", "holds"),
    [
        (ACME, DOCS, True),
        (ACME, GITHUB, True),
        (DOCS, GITHUB, True),
        (GITHUB, GITHUB, True),
        (DOCS, ACME, False),
        (GITHUB, DOCS, False),
        (DOCS, Owner(tenant_id="acme", workspace_id="ops"), False),
        (ACME, Owner(tenant_id="globex"), False),
        (GITHUB, Owner(tenant_id="acme", workspace_id="docs", connection_id="conn_gl"), False),
    ],
)
def test_an_owner_holds_what_is_within_it(owner: Owner, other: Owner, holds: bool) -> None:
    assert owner.holds(other) is holds


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"id": "sec_123", "purpose": "forge:token"}, "16 hex digits"),
        ({"id": "sec_0123456789ABCDEF", "purpose": "forge:token"}, "16 hex digits"),
        ({"id": "sec_0123456789abcdef", "purpose": "token"}, "family:name"),
    ],
)
def test_a_reference_has_an_opaque_id_and_a_purpose(fields: dict[str, Any], says: str) -> None:
    assert SecretRef(id="sec_0123456789abcdef", owner=ACME, purpose="litellm:key")
    with pytest.raises(ValidationError, match=says):
        SecretRef.model_validate({"owner": ACME} | fields)


def test_a_reader_reads_for_a_purpose() -> None:
    assert reader(session_id="s_1").session_id == "s_1"
    with pytest.raises(ValidationError, match="family:name"):
        reader(purpose="forge")


def test_a_value_is_kept_out_of_reprs() -> None:
    assert "ghp_first" not in repr(value())


# ─── The fake store ───────────────────────────────────────────────────────────


async def test_a_secret_is_put_and_read_by_a_reader_within_its_owner() -> None:
    store = FakeSecrets(clock=Clock())
    assert isinstance(store, Secrets)
    ref = await store.put(GITHUB, "forge:token", value(), rotate_every=timedelta(days=30))
    assert (ref.owner, ref.purpose) == (GITHUB, "forge:token")
    assert (await store.read(ref, reader=reader())).get_secret_value() == "ghp_first"
    assert store.reads == [FakeRead(ref, reader(), 1)]
    [listed] = await store.list(GITHUB)
    assert (listed.ref, listed.current, listed.created_at) == (ref, 1, NOW)
    assert listed.rotate_every == timedelta(days=30)


async def test_two_secrets_have_two_ids() -> None:
    store = FakeSecrets()
    first, second = (
        await store.put(ACME, "litellm:key", value()),
        await store.put(ACME, "litellm:key", value()),
    )
    assert first.id != second.id


@pytest.mark.parametrize(
    "outside",
    [
        reader(scope=Owner(tenant_id="globex", workspace_id="docs", connection_id="conn_gh")),
        reader(scope=Owner(tenant_id="acme", workspace_id="ops", connection_id="conn_gh")),
        reader(scope=Owner(tenant_id="acme", workspace_id="docs", connection_id="conn_gl")),
        reader(scope=DOCS),
        reader(purpose="litellm:key"),
    ],
)
async def test_a_reader_outside_its_owner_or_purpose_reads_nothing(outside: Reader) -> None:
    store = FakeSecrets()
    ref = await store.put(GITHUB, "forge:token", value())
    with pytest.raises(OutOfScope):
        await store.read(ref, reader=outside)
    assert store.reads == []


async def test_a_tenants_secret_is_read_in_any_of_its_workspaces() -> None:
    store = FakeSecrets()
    ref = await store.put(ACME, "litellm:key", value("sk-acme"))
    assert await store.read(ref, reader=reader(purpose="litellm:key"))


async def test_an_unknown_or_forged_reference_is_refused() -> None:
    store = FakeSecrets()
    ref = await store.put(GITHUB, "forge:token", value())
    never = SecretRef(id="sec_0000000000000000", owner=GITHUB, purpose="forge:token")
    moved = ref.model_copy(update={"owner": DOCS})
    with pytest.raises(UnknownSecret):
        await store.read(never, reader=reader())
    with pytest.raises(UnknownSecret):
        await store.read(moved, reader=reader(scope=GITHUB))
    with pytest.raises(UnknownSecret):
        await store.rotate(never, value(), grace=timedelta(minutes=5))
    with pytest.raises(UnknownSecret):
        await store.revoke(never, reason="leaked")


async def test_a_rotation_keeps_the_previous_version_readable_until_its_grace_ends() -> None:
    clock = Clock()
    store = FakeSecrets(clock=clock)
    ref = await store.put(GITHUB, "forge:token", value())
    clock.now = NOW + timedelta(days=1)
    rotated = await store.rotate(ref, value("ghp_second"), grace=timedelta(minutes=5))
    assert rotated == SecretVersion(
        ref=ref, number=2, created_at=clock.now, previous_until=clock.now + timedelta(minutes=5)
    )
    assert (await store.read(ref, reader=reader())).get_secret_value() == "ghp_second"
    assert (await store.read(ref, reader=reader(), version=1)).get_secret_value() == "ghp_first"
    assert (await store.read(ref, reader=reader(), version=2)).get_secret_value() == "ghp_second"
    [listed] = await store.list(GITHUB)
    assert (listed.current, listed.rotated_at) == (2, clock.now)
    clock.now += timedelta(minutes=5)
    with pytest.raises(VersionGone):
        await store.read(ref, reader=reader(), version=1)
    await store.rotate(ref, value("ghp_third"), grace=timedelta(minutes=5))
    with pytest.raises(VersionGone):
        await store.read(ref, reader=reader(), version=1)
    with pytest.raises(VersionGone):
        await store.read(ref, reader=reader(), version=4)


async def test_a_version_before_any_rotation_is_gone() -> None:
    store = FakeSecrets()
    ref = await store.put(GITHUB, "forge:token", value())
    with pytest.raises(VersionGone):
        await store.read(ref, reader=reader(), version=0)


async def test_a_revocation_ends_every_version_at_once() -> None:
    clock = Clock()
    store = FakeSecrets(clock=clock)
    ref = await store.put(GITHUB, "forge:token", value())
    await store.rotate(ref, value("ghp_second"), grace=timedelta(hours=1))
    await store.revoke(ref, reason="leaked in a log")
    for version in (None, 1, 2):
        with pytest.raises(Revoked, match="leaked in a log"):
            await store.read(ref, reader=reader(), version=version)
    with pytest.raises(Revoked):
        await store.rotate(ref, value("ghp_third"), grace=timedelta(hours=1))
    [listed] = await store.list(GITHUB)
    assert listed.revoked_at == NOW


async def test_deleting_an_owner_deletes_what_is_within_it() -> None:
    store = FakeSecrets()
    tenant = await store.put(ACME, "litellm:key", value())
    workspace = await store.put(DOCS, "webhook:signing", value())
    connection = await store.put(GITHUB, "forge:token", value())
    other = await store.put(Owner(tenant_id="acme", workspace_id="ops"), "forge:token", value())
    assert [listed.ref for listed in await store.list(DOCS)] == [workspace, connection]
    assert await store.delete_owned_by(DOCS) == 2
    assert [listed.ref for listed in await store.list(ACME)] == [tenant, other]
    with pytest.raises(UnknownSecret):
        await store.read(connection, reader=reader())
    assert await store.delete_owned_by(ACME) == 2


async def test_the_default_clock_is_the_systems_in_utc() -> None:
    store = FakeSecrets()
    await store.put(ACME, "litellm:key", value())
    [listed] = await store.list(ACME)
    assert abs(datetime.now(UTC) - listed.created_at) < timedelta(minutes=1)


# ─── The contract ─────────────────────────────────────────────────────────────


def test_the_contracts_schema_names_its_version_and_never_holds_a_value() -> None:
    schema = contract_schema()
    assert schema["title"] == f"lattice.secrets {CONTRACT}"
    assert schema["properties"] == {
        "ref": {"$ref": "#/$defs/SecretRef"},
        "reader": {"$ref": "#/$defs/Reader"},
        "version": {"$ref": "#/$defs/SecretVersion"},
        "metadata": {"$ref": "#/$defs/SecretMetadata"},
    }
