"""The secrets port's suite: what every :class:`~lattice_core.secrets.Secrets` adapter keeps.

:data:`SECRETS` checks a store the way the contract describes it: a value is read back only
within its owner and for its purpose, a reference that names another owner reads nothing, a
rotation keeps the previous version readable for its grace and no longer, a revocation ends
every version, a listing holds no value, and deleting an owner's secrets deletes theirs alone.

Each check works in tenants of its own, named ``conformance-`` and a random token, and deletes
every secret it put as it ends, pass or fail, so it runs against a deployment's store in use
(lattice ADR-0039).
"""

import secrets as tokens
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Final

from pydantic import SecretStr

from lattice_core.conformance import Check, Suite, expect, refuses
from lattice_core.secrets import (
    CONTRACT,
    OutOfScope,
    Owner,
    Reader,
    Revoked,
    SecretRef,
    Secrets,
    UnknownSecret,
    VersionGone,
)

__all__ = ["PURPOSE", "SECRETS"]

PURPOSE: Final = "conformance:check"
"""The purpose every secret the suite puts is for."""

_GRACE: Final = timedelta(hours=1)
"""A grace long enough that no check outlives it."""


def _store(built: object) -> Secrets:
    if not isinstance(built, Secrets):
        raise TypeError(f"{type(built).__name__} isn't a secrets store")
    return built


@asynccontextmanager
async def _tenant(store: Secrets) -> AsyncGenerator[Owner, None]:
    """A tenant of the check's own, whose every secret is deleted as the check ends."""
    owner = Owner(tenant_id=f"conformance-{tokens.token_hex(6)}")
    try:
        yield owner
    finally:
        await store.delete_owned_by(owner)


def _reader(scope: Owner, purpose: str = PURPOSE) -> Reader:
    return Reader(component="conformance", scope=scope, purpose=purpose)


def _value(token: str) -> SecretStr:
    return SecretStr(f"conformance-{token}-{tokens.token_hex(8)}")


async def _reads_back(store: Secrets) -> None:
    async with _tenant(store) as tenant:
        value = _value("first")
        ref = await store.put(tenant, PURPOSE, value)
        expect((ref.owner, ref.purpose) == (tenant, PURPOSE), f"put returned {ref!r}")
        read = await store.read(ref, reader=_reader(tenant))
        expect(read.get_secret_value() == value.get_secret_value(), "read another value")
        first = await store.read(ref, reader=_reader(tenant), version=1)
        expect(first.get_secret_value() == value.get_secret_value(), "version 1 isn't it")
        in_a_workspace = tenant.model_copy(update={"workspace_id": "w1"})
        await store.read(ref, reader=_reader(in_a_workspace))


async def _refuses_outside_its_owner(store: Secrets) -> None:
    async with _tenant(store) as tenant, _tenant(store) as other:
        ref = await store.put(tenant, PURPOSE, _value("scoped"))
        w1 = tenant.model_copy(update={"workspace_id": "w1"})
        in_w1 = await store.put(w1, PURPOSE, _value("w1"))
        own = w1.model_copy(update={"connection_id": "conn_1"})
        of_a_connection = await store.put(own, PURPOSE, _value("connection"))
        attempts = (
            (ref, _reader(other), "a read from another tenant"),
            (ref, _reader(tenant, "conformance:other"), "a read for another purpose"),
            (in_w1, _reader(tenant), "a read of a workspace's secret from its tenant at large"),
            (in_w1, _reader(w1.model_copy(update={"workspace_id": "w2"})), "a read from w2"),
            (of_a_connection, _reader(w1), "a read of a connection's secret without it"),
        )
        for secret, reader, what in attempts:
            await refuses(OutOfScope, store.read(secret, reader=reader), what)


async def _reads_nothing_by_a_forged_reference(store: Secrets) -> None:
    async with _tenant(store) as tenant, _tenant(store) as other:
        ref = await store.put(tenant, PURPOSE, _value("forged"))
        forged = SecretRef(id=ref.id, owner=other, purpose=PURPOSE)
        what = "a read by another tenant's reference to the secret's id"
        await refuses(UnknownSecret, store.read(forged, reader=_reader(other)), what)


async def _rotates_with_a_grace(store: Secrets) -> None:
    async with _tenant(store) as tenant:
        first, second = _value("before"), _value("after")
        ref = await store.put(tenant, PURPOSE, first)
        version = await store.rotate(ref, second, grace=_GRACE)
        expect(version.number == 2, f"the rotation made version {version.number}, not 2")
        current = await store.read(ref, reader=_reader(tenant))
        expect(current.get_secret_value() == second.get_secret_value(), "it isn't current")
        before = await store.read(ref, reader=_reader(tenant), version=1)
        expect(before.get_secret_value() == first.get_secret_value(), "version 1 is gone")
        ahead = store.read(ref, reader=_reader(tenant), version=3)
        await refuses(VersionGone, ahead, "a read of a version not yet made")


async def _ends_a_grace(store: Secrets) -> None:
    async with _tenant(store) as tenant:
        ref = await store.put(tenant, PURPOSE, _value("before"))
        await store.rotate(ref, _value("after"), grace=timedelta(0))
        past = store.read(ref, reader=_reader(tenant), version=1)
        await refuses(VersionGone, past, "a read of a version past its grace")


async def _revokes_every_version(store: Secrets) -> None:
    async with _tenant(store) as tenant:
        ref = await store.put(tenant, PURPOSE, _value("before"))
        await store.rotate(ref, _value("after"), grace=_GRACE)
        await store.revoke(ref, reason="conformance")
        reader = _reader(tenant)
        await refuses(Revoked, store.read(ref, reader=reader), "a read of a revoked secret")
        old = store.read(ref, reader=reader, version=1)
        await refuses(Revoked, old, "a read of a revoked secret's version in its grace")
        again = store.rotate(ref, _value("again"), grace=_GRACE)
        await refuses(Revoked, again, "a rotation of a revoked secret")
        [listed] = await store.list(tenant)
        expect(listed.revoked_at is not None, "its listing doesn't say it was revoked")


async def _lists_without_values(store: Secrets) -> None:
    async with _tenant(store) as tenant, _tenant(store) as other:
        value = _value("listed")
        ref = await store.put(tenant, PURPOSE, value, rotate_every=timedelta(days=30))
        w1 = tenant.model_copy(update={"workspace_id": "w1"})
        in_w1 = await store.put(w1, PURPOSE, _value("w1"))
        await store.put(other, PURPOSE, _value("other"))
        listed = await store.list(tenant)
        expect(
            sorted(m.ref.id for m in listed) == sorted((ref.id, in_w1.id)),
            "the tenant's listing isn't its own",
        )
        expect([m.ref for m in await store.list(w1)] == [in_w1], "w1's listing isn't w1's")
        [first] = [m for m in listed if m.ref == ref]
        expect(first.current == 1, f"a secret never rotated lists version {first.current}")
        expect(first.rotate_every == timedelta(days=30), "its rotation period isn't listed")
        shown = repr([m.model_dump() for m in listed])
        expect(value.get_secret_value() not in shown, "a listing holds a value")


async def _deletes_what_an_owner_holds(store: Secrets) -> None:
    async with _tenant(store) as tenant, _tenant(store) as other:
        w1 = tenant.model_copy(update={"workspace_id": "w1"})
        on_tenant = await store.put(tenant, PURPOSE, _value("tenant"))
        in_w1 = await store.put(w1, PURPOSE, _value("w1"))
        kept = await store.put(other, PURPOSE, _value("kept"))
        deleted = await store.delete_owned_by(w1)
        expect(deleted == 1, f"deleting w1's counted {deleted}, not 1")
        gone = store.read(in_w1, reader=_reader(w1))
        await refuses(UnknownSecret, gone, "a read of a workspace's secret it deleted")
        await store.read(on_tenant, reader=_reader(tenant))
        deleted = await store.delete_owned_by(tenant)
        expect(deleted == 1, f"deleting the tenant's counted {deleted}, not 1")
        await store.read(kept, reader=_reader(other))


async def _knows_no_unknown_secret(store: Secrets) -> None:
    async with _tenant(store) as tenant:
        ref = SecretRef(id=f"sec_{tokens.token_hex(8)}", owner=tenant, purpose=PURPOSE)
        reader = _reader(tenant)
        await refuses(UnknownSecret, store.read(ref, reader=reader), "a read of no secret")
        rotation = store.rotate(ref, _value("none"), grace=_GRACE)
        await refuses(UnknownSecret, rotation, "a rotation of no secret")
        revocation = store.revoke(ref, reason="conformance")
        await refuses(UnknownSecret, revocation, "a revocation of no secret")


SECRETS: Final = Suite[Secrets](
    port="secrets",
    version=CONTRACT,
    kind="secrets",
    built=_store,
    checks=(
        Check("a value put is read back within its owner, for its purpose", _reads_back),
        Check(
            "a reader outside its owner, or for another purpose, is refused",
            _refuses_outside_its_owner,
        ),
        Check(
            "a reference naming another owner reads nothing", _reads_nothing_by_a_forged_reference
        ),
        Check(
            "a rotation keeps the previous version readable for its grace", _rotates_with_a_grace
        ),
        Check("a version past its grace isn't readable", _ends_a_grace),
        Check("a revocation ends every version", _revokes_every_version),
        Check("a listing is every secret within the owner, and no value", _lists_without_values),
        Check(
            "deleting what an owner holds deletes it alone, and counts it",
            _deletes_what_an_owner_holds,
        ),
        Check("a reference to no secret is unknown", _knows_no_unknown_secret),
    ),
)
"""The secrets port's suite, for every :class:`~lattice_core.secrets.Secrets` adapter."""
