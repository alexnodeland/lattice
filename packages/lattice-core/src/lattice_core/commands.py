"""Commands: every action a person can take in portalr, declared once for every surface.

A :class:`Command` is a lattice RFC-0011 :class:`~lattice_core.capabilities.Capability`, a
``command`` capability called only through the enforcer, plus what a surface needs and the
registry doesn't: the toolset it is grouped in, whether it is a tool, a resource or both (or
:class:`NotExposed`, with a reason), portalr's route that each result links to, the URI
template of a read exposed as a resource, and the surfaces it is offered on (lattice RFC-0014,
ADR-0041).

Each package declares a static catalog, :class:`Commands`, with no I/O and no scope, so the
parity test, the schemas and the docs read it without a database; the application binds it to
its runtime at its composition root, where the bound provider also answers ``Commands``.
:func:`catalog` composes catalogs and refuses two commands of one name, or of one tool name: a
command's MCP tool name is ``<package>_<name>`` (:func:`tool_name`), since some clients refuse a
dot. A breaking change is a new command, ``<package>.<name>_v2``, beside the old one.

Every operation of a library's OpenAPI document says what it calls in its :data:`EXTENSION`,
``x-lattice-command`` (lattice ADR-0042): a command (:func:`calls`), the member of its body that
carries command frames, whose ``type`` names the action (:func:`carries_frames`), or why it calls
none (:func:`calls_none`). :func:`called` reads it back, for the parity test.

The contract's version is :data:`CONTRACT`, and its JSON Schema, which :func:`contract_schema`
returns, is checked in at ``schemas/commands.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import re
from collections.abc import AsyncIterator, Iterable
from types import MappingProxyType
from typing import Annotated, Final, Literal, Protocol, Self, get_args, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from lattice_core.capabilities import Capability, Scope

__all__ = [
    "COMMAND_NAME",
    "CONTRACT",
    "EXTENSION",
    "SURFACES",
    "TOOLSETS",
    "TOOL_NAME",
    "Command",
    "Commands",
    "Exposure",
    "Frames",
    "NoCommand",
    "NotExposed",
    "ResourceChanged",
    "Surface",
    "Toolset",
    "Watch",
    "called",
    "calls",
    "calls_none",
    "carries_frames",
    "catalog",
    "contract_schema",
    "tool_name",
]

CONTRACT: Final = "1.1.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field, a new :data:`Toolset` or a new :data:`Surface` is a minor one."""

Toolset = Literal["core", "automations", "research", "code", "files", "feedback", "admin"]
"""The group a command is offered in, which a client turns on or off as a whole (#919)."""

TOOLSETS: Final[tuple[Toolset, ...]] = get_args(Toolset)
"""The toolsets."""

Exposure = Literal["tool", "resource", "both"]
"""How an outside client reaches a command: as a tool it calls, a resource it reads, or both."""

Surface = Literal["portalr", "mcp", "acp", "webmcp"]
"""Where a command is offered: portalr, an MCP or ACP client, or a browser agent (WebMCP)."""

SURFACES: Final[frozenset[Surface]] = frozenset(get_args(Surface))
"""Every surface: where a command is offered unless it says otherwise."""

COMMAND_NAME: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
"""A command's name: its package, one dot and its name, such as ``artifactr.post_message``."""

TOOL_NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")
"""An MCP tool name, as a command's makes it: lowercase, digits and underscores, at most 64."""


def tool_name(name: str, /) -> str:
    """Return a command's MCP tool name: its name with its dot as an underscore.

    ``artifactr.post_message`` is ``artifactr_post_message``.
    """
    return name.replace(".", "_", 1)


class NotExposed(BaseModel):
    """A command no outside client reaches, and why: what the parity test asks of it.

    Raises:
        ValueError: If the reason is empty.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    reason: str = Field(min_length=1)
    """Why it isn't a tool or a resource: "approvals come from a person"."""


class Command(BaseModel):
    """An action a person can take in portalr, as every surface offers it.

    Raises:
        ValueError: If its capability isn't a ``command`` capability, its name isn't of
            :data:`COMMAND_NAME`'s form or makes a tool name too long, it is exposed as a
            resource without a URI template or offered on no surface, a resource is given to
            one that is only a tool, or a tenant-wide one's route or resource names a
            workspace.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    capability: Capability
    """The capability it is: its name, version, schemas, tier, effects, reversibility, gate,
    limits and risk class (lattice RFC-0011). Its description is written for a model choosing a
    tool."""
    toolset: Toolset
    """The one toolset it is offered in."""
    exposure: Exposure | NotExposed
    """How an outside client reaches it, or why none does."""
    route: str | None
    """portalr's path for a link to what it acts on, such as
    ``/t/{tenant}/w/{workspace}/threads/{thread_id}``, or None for none."""
    resource: str | None = None
    """The URI template of a read exposed as a resource, such as
    ``artifactr://{tenant}/{workspace}/artifacts/{artifact_id}``."""
    surfaces: frozenset[Surface] = SURFACES
    """The surfaces it is offered on: every one, unless it is portalr's alone or the like."""
    tenant_wide: bool = False
    """Whether it acts on the tenant as a whole, such as listing its workspaces or granting a
    role, rather than in one of its workspaces: it is called with a scope that names no
    workspace, and a surface asks its caller for none (lattice ADR-0044)."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        name = self.capability.name
        if self.capability.provider != "command":
            raise ValueError(f"{name} is a {self.capability.provider} capability, not a command")
        if not COMMAND_NAME.fullmatch(name):
            raise ValueError(f"a command's name is <package>.<name>, not {name!r}")
        if not TOOL_NAME.fullmatch(tool_name(name)):
            raise ValueError(f"{name} makes a tool name longer than 64 characters")
        exposed = self.exposure if isinstance(self.exposure, str) else None
        if exposed in ("resource", "both") and self.resource is None:
            raise ValueError(f"{name} is exposed as a resource, so it names its URI template")
        if self.resource is not None and exposed not in ("resource", "both"):
            raise ValueError(f"{name} names a resource, so it is exposed as one")
        if not self.surfaces:
            raise ValueError(f"{name} is offered on some surface")
        if self.tenant_wide and "{workspace}" in f"{self.route or ''}{self.resource or ''}":
            raise ValueError(f"{name} is tenant-wide, so its route and resource name no workspace")
        return self

    @property
    def name(self) -> str:
        """Its name, its capability's: ``artifactr.post_message``."""
        return self.capability.name

    @property
    def tool(self) -> str:
        """Its MCP tool name: ``artifactr_post_message``."""
        return tool_name(self.name)


@runtime_checkable
class Commands(Protocol):
    """A package's static catalog: every command it declares, with no I/O and no scope."""

    def commands(self) -> Iterable[Command]:
        """Return its commands."""
        ...


class ResourceChanged(BaseModel):
    """A resource whose content changed, for a client that subscribed to it."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    uri: str = Field(min_length=1)
    """The resource's URI, as its command's ``resource`` template makes it."""


@runtime_checkable
class Watch(Protocol):
    """The resources that change in a scope: answered by a bound provider, never the catalog."""

    def changes(self, scope: Scope, /) -> AsyncIterator[ResourceChanged]:
        """Yield each resource that changes in the scope, as it changes."""
        ...


def catalog(*catalogs: Commands) -> MappingProxyType[str, Command]:
    """Return the commands of every catalog, by name, in the order given.

    Raises:
        ValueError: If two commands share a name, or a tool name.
    """
    found: dict[str, Command] = {}
    tools: dict[str, str] = {}
    for each in catalogs:
        for command in each.commands():
            if command.name in found:
                raise ValueError(f"two commands are named {command.name}")
            if command.tool in tools:
                raise ValueError(
                    f"{command.name} and {tools[command.tool]} are both the tool {command.tool}"
                )
            found[command.name] = command
            tools[command.tool] = command.name
    return MappingProxyType(found)


EXTENSION: Final = "x-lattice-command"
"""The OpenAPI extension on every operation of a library's document: what the operation calls
(lattice ADR-0042)."""


class Frames(BaseModel):
    """An operation whose body carries command frames: the member that holds one.

    The frame's ``type`` names the action it asks, as on the stream, so the parity test holds each
    ``type`` the frame union names to some command's gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)

    frames: str = Field(min_length=1)
    """The body's member that holds a frame, such as ``command``."""
    none: dict[str, Annotated[str, Field(min_length=1)]] = Field(default_factory=dict[str, str])
    """Each frame ``type`` that asks no action, and why, such as a subscription the stream
    alone serves."""


class NoCommand(BaseModel):
    """An operation that calls no command, and why: no action, or a command still to come."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)

    none: str = Field(min_length=1)
    """Why: "the UIs' configuration, which anyone may read", or the issue a command comes in."""


_Name = Annotated[str, StringConstraints(pattern=f"^{COMMAND_NAME.pattern}$")]

_CALLED: Final = TypeAdapter[_Name | list[_Name] | Frames | NoCommand](
    _Name | Annotated[list[_Name], Field(min_length=2)] | Frames | NoCommand
)


def calls(command: str, /, *more: str) -> dict[str, JsonValue]:
    """Return the ``openapi_extra`` of an operation that calls a command.

    An operation that calls one of several, by its arguments, names each, such as grantr's grant
    of a role on a workspace or on the tenant.

    Raises:
        ValueError: If a name isn't of :data:`COMMAND_NAME`'s form.
    """
    names = (command, *more)
    if malformed := [name for name in names if not COMMAND_NAME.fullmatch(name)]:
        raise ValueError(f"a command's name is <package>.<name>, not {malformed[0]!r}")
    return {EXTENSION: list(names) if more else command}


def carries_frames(member: str, /, **none: str) -> dict[str, JsonValue]:
    """Return the ``openapi_extra`` of an operation whose body's ``member`` is a command frame.

    Args:
        member: The body's member that holds the frame.
        **none: Each frame ``type`` that asks no action, and why.

    Raises:
        ValueError: If a reason is empty.
    """
    return {EXTENSION: Frames(frames=member, none=none).model_dump()}


def calls_none(reason: str, /) -> dict[str, JsonValue]:
    """Return the ``openapi_extra`` of an operation that calls no command, and why.

    Raises:
        ValueError: If the reason is empty.
    """
    return {EXTENSION: NoCommand(none=reason).model_dump()}


def called(extension: JsonValue, /) -> tuple[str, ...] | Frames | NoCommand:
    """Read what an operation's :data:`EXTENSION` says it calls: commands' names, or else.

    Raises:
        ValueError: If it says none of what :func:`calls`, :func:`carries_frames` and
            :func:`calls_none` write, or is missing.
    """
    found = _CALLED.validate_python(extension)
    if isinstance(found, str):
        return (found,)
    if isinstance(found, list):
        return tuple(found)
    return found


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: a command."""
    schema = Command.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.commands {CONTRACT}",
        "description": (
            "lattice's commands contract: an action a person can take in portalr, as an "
            "RFC-0011 capability with the toolset, exposure, route, resource and surfaces "
            "every surface offers it by."
        ),
        "type": "object",
        "properties": schema["properties"],
        "required": schema["required"],
        "$defs": schema["$defs"],
    }
