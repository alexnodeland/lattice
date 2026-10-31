"""Secrets: tokens, keys and signing secrets, held by a store and referred to everywhere else.

Everything but the store keeps a :class:`SecretRef`: an opaque id, its :class:`Owner` (a
tenant, and optionally one of its workspaces and one connection) and its purpose, such as
``forge:token``. A value is read only by the component that uses it, at the moment it uses it,
through :meth:`Secrets.read`, which checks the :class:`Reader`'s scope against the owner before
it touches the store, and is audited. A rotation keeps the previous version readable for a
grace period, so a follower holding it finishes; a revocation ends every version at once; and
deleting a connection, a workspace or a tenant deletes what it owns (lattice RFC-0011).

This module declares the contract: the reference, the :class:`Secrets` port, and its refusals.
Its adapters are extras (Supabase Vault, behind ``sql``, and AWS Secrets Manager; lattice
ADR-0034); :class:`FakeSecrets` is an in-memory store for tests, with the same semantics.

The contract's version is :data:`CONTRACT`, and its JSON Schema, which :func:`contract_schema`
returns, is checked in at ``schemas/secrets.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import re
import secrets as tokens
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol, Self, runtime_checkable

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    model_validator,
)

__all__ = [
    "CONTRACT",
    "PURPOSE",
    "SECRET_ID",
    "FakeRead",
    "FakeSecrets",
    "OutOfScope",
    "Owner",
    "Reader",
    "Revoked",
    "SecretError",
    "SecretId",
    "SecretMetadata",
    "SecretRef",
    "SecretVersion",
    "Secrets",
    "UnknownSecret",
    "VersionGone",
    "contract_schema",
]

CONTRACT: Final = "1.0.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field is a minor one."""

SECRET_ID: Final = re.compile(r"sec_[0-9a-f]{16}")
"""A secret's id: ``sec_`` and 16 hexadecimal digits, opaque."""

PURPOSE: Final = re.compile(r"[a-z][a-z0-9-]*:[a-z][a-z0-9-]*")
"""A purpose's form: a family, a colon and a name, such as ``forge:token``, ``connector:oauth``,
``mcp:oauth``, ``litellm:key`` or ``webhook:signing``."""

type SecretId = str
"""A secret's id, of :data:`SECRET_ID`'s form."""


class Owner(BaseModel):
    """What a secret belongs to: a tenant, and optionally one of its workspaces and a connection.

    A secret is valid only within its owner: a tenant's in any of its workspaces, a workspace's
    only in that workspace, a connection's only for that connection.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    tenant_id: str
    """The tenant it belongs to."""
    workspace_id: str | None = None
    """The workspace it belongs to, or None for the whole tenant."""
    connection_id: str | None = None
    """The connection it belongs to, or None for none in particular."""

    def holds(self, other: "Owner") -> bool:
        """Whether the other is within this owner: in its tenant, workspace and connection."""
        return (
            self.tenant_id == other.tenant_id
            and self.workspace_id in (None, other.workspace_id)
            and self.connection_id in (None, other.connection_id)
        )


class SecretRef(BaseModel):
    """A reference to a secret, which everything but the store keeps instead of its value.

    Raises:
        ValueError: If the id isn't of :data:`SECRET_ID`'s form or the purpose of
            :data:`PURPOSE`'s.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    id: SecretId
    """Its id, opaque."""
    owner: Owner
    """What it belongs to."""
    purpose: str
    """What it is for, such as ``forge:token``."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not SECRET_ID.fullmatch(self.id):
            raise ValueError(f"a secret's id is sec_ and 16 hex digits, not {self.id!r}")
        if not PURPOSE.fullmatch(self.purpose):
            raise ValueError(f"a purpose is family:name, not {self.purpose!r}")
        return self


class Reader(BaseModel):
    """Who reads a secret's value, as the audit records it: never the value.

    Raises:
        ValueError: If the purpose isn't of :data:`PURPOSE`'s form.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    component: str
    """The component that reads it, such as ``egress``, ``credential-proxy`` or a connector's
    follower."""
    scope: Owner
    """Where it reads: the tenant, and the workspace and connection it acts for. A secret is read
    only where this is within its owner."""
    purpose: str
    """What it reads for; only a secret of the same purpose is read."""
    session_id: str | None = None
    """The code session it reads for, if it reads for one."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not PURPOSE.fullmatch(self.purpose):
            raise ValueError(f"a purpose is family:name, not {self.purpose!r}")
        return self


class SecretVersion(BaseModel):
    """A version of a secret, as a rotation made it current."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    ref: SecretRef
    """The secret."""
    number: int = Field(ge=1)
    """Its number: the first value is 1, and each rotation adds one."""
    created_at: AwareDatetime
    """When it was made current."""
    previous_until: AwareDatetime | None = None
    """Until when the version before it stays readable, or None if there was none."""


class SecretMetadata(BaseModel):
    """What may be listed of a secret: never its value."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    ref: SecretRef
    """The secret."""
    current: int = Field(ge=1)
    """The number of its current version."""
    created_at: AwareDatetime
    """When it was put."""
    rotated_at: AwareDatetime | None = None
    """When it was last rotated, if it was."""
    rotate_every: timedelta | None = None
    """How often it is to be rotated, where its provider supports it."""
    revoked_at: AwareDatetime | None = None
    """When it was revoked, if it was."""


class SecretError(Exception):
    """A secrets store refused what was asked of it."""


class UnknownSecret(SecretError, LookupError):
    """No secret of the reference, or no longer: it was deleted, or never put."""


class OutOfScope(SecretError):
    """The reader isn't within the secret's owner, or reads for another purpose."""


class Revoked(SecretError):
    """The secret was revoked: no version of it is readable."""


class VersionGone(SecretError):
    """The version asked for isn't readable: it is past its grace period, or never was."""


@runtime_checkable
class Secrets(Protocol):
    """Where secrets are kept: Supabase Vault, AWS Secrets Manager, or a fake.

    Its arguments before the ``*`` are positional, so an implementation names them as it likes.
    """

    async def put(
        self,
        owner: Owner,
        purpose: str,
        value: SecretStr,
        /,
        *,
        rotate_every: timedelta | None = None,
    ) -> SecretRef:
        """Keep a value for the owner and purpose, and return its reference."""
        ...

    async def read(
        self, ref: SecretRef, /, *, reader: Reader, version: int | None = None
    ) -> SecretStr:
        """Return the current value, or a version still readable, for the reader; audited.

        Raises:
            UnknownSecret: If there is no such secret.
            OutOfScope: If the reader isn't within its owner, or reads for another purpose.
            Revoked: If it was revoked.
            VersionGone: If the version asked for isn't readable.
        """
        ...

    async def rotate(
        self, ref: SecretRef, value: SecretStr, /, *, grace: timedelta
    ) -> SecretVersion:
        """Make a new value current, keeping the previous one readable for the grace period.

        Raises:
            UnknownSecret: If there is no such secret.
            Revoked: If it was revoked.
        """
        ...

    async def revoke(self, ref: SecretRef, /, *, reason: str) -> None:
        """End every version at once, on a leak or when it is no longer wanted.

        Raises:
            UnknownSecret: If there is no such secret.
        """
        ...

    async def list(self, owner: Owner, /) -> list[SecretMetadata]:
        """Return what may be listed of every secret within the owner: never a value."""
        ...

    async def delete_owned_by(self, owner: Owner, /) -> int:
        """Delete every secret within the owner, and return how many."""
        ...


@dataclass
class _Held:
    metadata: SecretMetadata
    values: dict[int, SecretStr]
    previous_until: datetime | None = None
    revoked: str | None = None


@dataclass(frozen=True)
class FakeRead:
    """A read a :class:`FakeSecrets` allowed: what and by whom, never the value."""

    ref: SecretRef
    reader: Reader
    version: int


class FakeSecrets:
    """An in-memory secrets store for tests, with the semantics its adapters keep.

    It checks a reader's scope and purpose before it looks a value up, records each read it
    allows in :attr:`reads`, keeps a rotated-out version readable until its grace ends by the
    clock given, and ends every version at once on revocation.

    Args:
        clock: The time now; the system's, in UTC, if omitted.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._held: dict[SecretId, _Held] = {}
        self.reads: list[FakeRead] = []
        """Every read it allowed, in order."""

    def _get(self, ref: SecretRef) -> _Held:
        held = self._held.get(ref.id)
        if held is None or held.metadata.ref != ref:
            raise UnknownSecret(f"no secret {ref.id}")
        return held

    async def put(
        self,
        owner: Owner,
        purpose: str,
        value: SecretStr,
        /,
        *,
        rotate_every: timedelta | None = None,
    ) -> SecretRef:
        """Keep a value for the owner and purpose, and return its reference."""
        ref = SecretRef(id=f"sec_{tokens.token_hex(8)}", owner=owner, purpose=purpose)
        metadata = SecretMetadata(
            ref=ref, current=1, created_at=self._clock(), rotate_every=rotate_every
        )
        self._held[ref.id] = _Held(metadata=metadata, values={1: value})
        return ref

    async def read(
        self, ref: SecretRef, /, *, reader: Reader, version: int | None = None
    ) -> SecretStr:
        """Return the current value, or a version still readable, for the reader; recorded.

        Raises:
            UnknownSecret: If there is no such secret.
            OutOfScope: If the reader isn't within its owner, or reads for another purpose.
            Revoked: If it was revoked.
            VersionGone: If the version asked for isn't readable.
        """
        if not ref.owner.holds(reader.scope) or reader.purpose != ref.purpose:
            raise OutOfScope(f"{reader.component} may not read {ref.id}")
        held = self._get(ref)
        if held.revoked is not None:
            raise Revoked(f"{ref.id} was revoked: {held.revoked}")
        current = held.metadata.current
        number = current if version is None else version
        readable = number == current or (
            number == current - 1
            and held.previous_until is not None
            and self._clock() < held.previous_until
        )
        if not readable:
            raise VersionGone(f"version {number} of {ref.id} isn't readable")
        self.reads.append(FakeRead(ref, reader, number))
        return held.values[number]

    async def rotate(
        self, ref: SecretRef, value: SecretStr, /, *, grace: timedelta
    ) -> SecretVersion:
        """Make a new value current, keeping the previous one readable for the grace period.

        Raises:
            UnknownSecret: If there is no such secret.
            Revoked: If it was revoked.
        """
        held = self._get(ref)
        if held.revoked is not None:
            raise Revoked(f"{ref.id} was revoked: {held.revoked}")
        now = self._clock()
        number = held.metadata.current + 1
        held.values = {held.metadata.current: held.values[held.metadata.current], number: value}
        held.previous_until = now + grace
        held.metadata = held.metadata.model_copy(update={"current": number, "rotated_at": now})
        return SecretVersion(ref=ref, number=number, created_at=now, previous_until=now + grace)

    async def revoke(self, ref: SecretRef, /, *, reason: str) -> None:
        """End every version at once.

        Raises:
            UnknownSecret: If there is no such secret.
        """
        held = self._get(ref)
        held.revoked = reason
        held.values.clear()
        held.metadata = held.metadata.model_copy(update={"revoked_at": self._clock()})

    async def list(self, owner: Owner, /) -> list[SecretMetadata]:
        """Return what may be listed of every secret within the owner, in the order put."""
        return [
            held.metadata for held in self._held.values() if owner.holds(held.metadata.ref.owner)
        ]

    async def delete_owned_by(self, owner: Owner, /) -> int:
        """Delete every secret within the owner, and return how many."""
        gone = [id for id, held in self._held.items() if owner.holds(held.metadata.ref.owner)]
        for id in gone:
            del self._held[id]
        return len(gone)


class _Contract(BaseModel):
    ref: SecretRef
    reader: Reader
    version: SecretVersion
    metadata: SecretMetadata


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: a reference, a reader, a version and what is listed."""
    schema = _Contract.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.secrets {CONTRACT}",
        "description": (
            "lattice's secrets contract: `ref` is what everything but the store keeps, `reader` "
            "who reads a value, `version` what a rotation made current, and `metadata` what may "
            "be listed of a secret, never its value."
        ),
        "type": "object",
        "properties": schema["properties"],
        "$defs": schema["$defs"],
    }
