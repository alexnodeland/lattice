"""Bindings: which of a source's events reach which workspace (lattice RFC-0013, RFC-0011's O13).

A :class:`Binding` names a source, such as ``tracker`` or ``alertmanager``, one of its
connections, and the workspace its events reach there: what it selects by (the source's declared
selectors, such as a repository or a project), which of the source's types it receives, the
:data:`Trust` it lowers the source's level to here, never raising it, and the source's own
options, such as a tracker's default labels. Three packages read them and import none of one
another, reflexr's intake, relayr's trackers and the code sessions' repositories, so the type
and its port, :class:`Bindings`, are declared here, as integrations and settings are. grantr
stores the tenant's, beside the operator's layer in the deployment's configuration (lattice
ADR-0040); :class:`FakeBindings` holds them in memory, for tests.

The contract's version is :data:`CONTRACT`, and its JSON Schema, which :func:`contract_schema`
returns, is checked in at ``schemas/bindings.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import re
from collections.abc import Sequence
from typing import Final, Literal, Protocol, Self, get_args, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from lattice_core.capabilities import JsonObject

__all__ = [
    "BINDING_ID",
    "CONTRACT",
    "SOURCE",
    "TRUST_LEVELS",
    "Binding",
    "BindingId",
    "Bindings",
    "FakeBindings",
    "Trust",
    "contract_schema",
    "lowest",
]

CONTRACT: Final = "1.0.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field is a minor one."""

BINDING_ID: Final = re.compile(r"bnd_[0-9a-f]{16}")
"""A binding's id: ``bnd_`` and 16 hexadecimal digits, opaque."""

SOURCE: Final = re.compile(r"[a-z][a-z0-9-]*")
"""A source's name, as its spec names it: lowercase letters, digits and hyphens."""

type BindingId = str
"""A binding's id, of :data:`BINDING_ID`'s form."""

Trust = Literal["untrusted", "authenticated", "internal"]
"""How far an event is trusted, lowest first: content anyone outside the tenant can write,
content an identified member wrote through a surface that authenticated them, or what lattice
or the stack the operator runs wrote (lattice RFC-0013)."""

TRUST_LEVELS: Final[tuple[Trust, ...]] = get_args(Trust)
"""The levels of :data:`Trust`, lowest first."""


def lowest(level: Trust, /, *levels: Trust | None) -> Trust:
    """Return the lowest of the levels given, ignoring None: each step of a level only lowers it.

    A binding's ``trust`` lowers its source's level here (``lowest(source, binding.trust)``),
    and an occurrence's lowers it further.
    """
    given: list[Trust] = [level, *(each for each in levels if each is not None)]
    return min(given, key=TRUST_LEVELS.index)


class Binding(BaseModel):
    """Which of a source's events, on one of its connections, reach one workspace of a tenant.

    Raises:
        ValueError: If the id isn't of :data:`BINDING_ID`'s form, the source's name isn't of
            :data:`SOURCE`'s, or it receives no type at all: None receives every type.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    id: BindingId
    """Its id, opaque."""
    tenant_id: str = Field(min_length=1)
    """The tenant whose workspace it reaches."""
    workspace_id: str = Field(min_length=1)
    """The workspace the events reach."""
    source: str
    """The source's name, as its spec names it: ``tracker``, ``alertmanager``, ``forge``."""
    connection: str = Field(min_length=1)
    """The id of the source's connection it binds, such as a tracker's project or an
    installation."""
    select: JsonObject = Field(default_factory=dict[str, JsonValue])
    """What it selects by, in the source's declared selectors, such as ``{"repository":
    "acme/api"}``: validated against the source's select schema; empty selects everything."""
    types: frozenset[str] | None = None
    """The event types it receives; None receives every type the source has."""
    trust: Trust | None = None
    """The level it lowers the source's to here, never raising it; None keeps the source's."""
    options: JsonObject = Field(default_factory=dict[str, JsonValue])
    """The source's own options, such as a tracker's default labels."""
    bound_at: AwareDatetime
    """When it was bound: there is no history before it."""
    by: str = Field(min_length=1)
    """Who bound it: the operator, or the grantr subject who did, such as ``user:alice``."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not BINDING_ID.fullmatch(self.id):
            raise ValueError(f"a binding's id is bnd_ and 16 hex digits, not {self.id!r}")
        if not SOURCE.fullmatch(self.source):
            raise ValueError(f"a source's name is lowercase and hyphens, not {self.source!r}")
        if self.types is not None and not self.types:
            raise ValueError("a binding receives some types, or every one with types=None")
        return self

    def level(self, source: Trust, /) -> Trust:
        """The level the source's events have through it: the source's, or its own if lower."""
        return lowest(source, self.trust)


@runtime_checkable
class Bindings(Protocol):
    """Where bindings are kept: grantr's store, with the operator's layer, or a fake.

    Its arguments are positional, so an implementation names them as it likes.
    """

    async def for_connection(self, source: str, connection: str, /) -> Sequence[Binding]:
        """Return every binding of the source's connection, in every tenant.

        It is what the intake routes an occurrence by.
        """
        ...

    async def for_workspace(self, tenant_id: str, workspace_id: str, /) -> Sequence[Binding]:
        """Return every binding that reaches the tenant's workspace, of every source."""
        ...


class FakeBindings:
    """Bindings held in memory, for tests, in the order they were bound.

    Args:
        bindings: The bindings it starts with.

    Raises:
        ValueError: If two bindings share an id.
    """

    def __init__(self, *bindings: Binding) -> None:
        self._bindings: dict[BindingId, Binding] = {}
        for binding in bindings:
            self.bind(binding)

    def bind(self, binding: Binding, /) -> None:
        """Keep a binding.

        Raises:
            ValueError: If one of its id is kept already.
        """
        if binding.id in self._bindings:
            raise ValueError(f"binding {binding.id} is bound already")
        self._bindings[binding.id] = binding

    def unbind(self, id: BindingId, /) -> None:
        """Remove a binding.

        Raises:
            KeyError: If none of the id is kept.
        """
        del self._bindings[id]

    async def for_connection(self, source: str, connection: str, /) -> list[Binding]:
        """Return every binding of the source's connection, in the order they were bound."""
        return [
            b for b in self._bindings.values() if (b.source, b.connection) == (source, connection)
        ]

    async def for_workspace(self, tenant_id: str, workspace_id: str, /) -> list[Binding]:
        """Return every binding that reaches the workspace, in the order they were bound."""
        here = (tenant_id, workspace_id)
        return [b for b in self._bindings.values() if (b.tenant_id, b.workspace_id) == here]


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: a binding."""
    schema = Binding.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.bindings {CONTRACT}",
        "description": (
            "lattice's bindings contract: which of a source's events, on one of its "
            "connections, reach one workspace of a tenant, and the trust it lowers them to."
        ),
        "type": "object",
        "properties": schema["properties"],
        "required": schema["required"],
        "$defs": schema["$defs"],
    }
