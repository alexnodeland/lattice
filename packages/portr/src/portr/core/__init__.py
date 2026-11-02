"""portr's core: what an outside client is offered, made from the composed commands.

No I/O and no MCP SDK. :func:`offered` turns lattice's commands (lattice-core's ``Command``, lattice
ADR-0041) into the tools and resource templates a client sees, for the toolsets its connection
may use: each command offered on the ``mcp`` surface and exposed as a tool, a resource or both, in
one of those toolsets. ``core`` is always among them (lattice RFC-0014). A tool's name is its
command's tool name, ``<package>_<name>``, and its annotations follow from the command's tier,
reversibility and effects, so a client can tell a read from a change it can't undo.
:func:`tiers` says which tiers each toolset holds, as the consent page shows them.
"""

from collections.abc import Collection, Iterable, Mapping
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from lattice_core.capabilities import JsonObject, Tier
from lattice_core.commands import TOOLSETS, Command, NotExposed, Surface, Toolset

__all__ = [
    "CORE",
    "SURFACE",
    "Annotations",
    "Offered",
    "Resource",
    "Tool",
    "offered",
    "tiers",
]

CORE: Final[Toolset] = "core"
"""The toolset every connection may use, whatever else it was given."""

SURFACE: Final[Surface] = "mcp"
"""The surface portr's MCP server offers commands on."""


class Annotations(BaseModel):
    """What a tool tells a client of itself, as MCP's tool annotations say it.

    Each is a hint, never a guarantee: the enforcer decides every call.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, use_attribute_docstrings=True)

    read_only: bool = Field(serialization_alias="readOnlyHint")
    """It changes nothing: its command's tier is ``read``."""
    destructive: bool = Field(serialization_alias="destructiveHint")
    """A change it makes can't be undone: its command is ``irreversible``."""
    idempotent: bool = Field(serialization_alias="idempotentHint")
    """Calling it again with the same arguments changes nothing more: a read."""
    open_world: bool = Field(serialization_alias="openWorldHint")
    """It reaches beyond the deployment: it sends data out or reads untrusted content."""


class Tool(BaseModel):
    """A tool a client is offered: one command, as MCP's ``tools/list`` names it."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    name: str
    """The command's tool name, ``<package>_<name>``."""
    command: str
    """The command's name, ``<package>.<name>``, which every call goes through."""
    description: str
    input_schema: JsonObject
    annotations: Annotations
    toolset: Toolset
    route: str | None
    """portalr's path that a result links to, its placeholders unfilled."""
    tenant_wide: bool = False
    """It acts on the tenant as a whole, so a client names no workspace for it (lattice
    ADR-0044)."""


class Resource(BaseModel):
    """A resource template a client is offered: one read, by the URI its command names."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    uri_template: str
    command: str
    """The read's command, which every read of a resource goes through."""
    name: str
    """The command's tool name."""
    description: str
    toolset: Toolset


class Offered(BaseModel):
    """What a client is offered: the tools and the resource templates, in the catalogs' order."""

    model_config = ConfigDict(frozen=True)

    tools: tuple[Tool, ...]
    resources: tuple[Resource, ...]


def _annotations(command: Command) -> Annotations:
    capability = command.capability
    read = capability.tier == "read"
    return Annotations(
        read_only=read,
        destructive=not read and capability.reversibility == "irreversible",
        idempotent=read,
        open_world=bool({"sends_out", "reads_untrusted"} & capability.effects),
    )


def _reached(command: Command, toolsets: frozenset[Toolset]) -> bool:
    return (
        not isinstance(command.exposure, NotExposed)
        and SURFACE in command.surfaces
        and command.toolset in toolsets
    )


def offered(commands: Iterable[Command], *, toolsets: Collection[Toolset] = ()) -> Offered:
    """Return the tools and resource templates a connection with these toolsets is offered.

    Args:
        commands: Every command of the composed catalogs, as the registry lists them.
        toolsets: The toolsets the connection may use; ``core`` is added to them.

    Raises:
        ValueError: If a toolset isn't one of lattice-core's.
    """
    if unknown := sorted(set(toolsets) - set(TOOLSETS)):
        raise ValueError(f"no toolset {unknown[0]!r}")
    reach = frozenset(toolsets) | frozenset[Toolset]((CORE,))
    tools: list[Tool] = []
    resources: list[Resource] = []
    for command in commands:
        if not _reached(command, reach):
            continue
        capability = command.capability
        if command.exposure in ("tool", "both"):
            tools.append(
                Tool(
                    name=command.tool,
                    command=command.name,
                    description=capability.description,
                    input_schema=capability.input_schema,
                    annotations=_annotations(command),
                    toolset=command.toolset,
                    route=command.route,
                    tenant_wide=command.tenant_wide,
                )
            )
        if command.resource is not None:
            resources.append(
                Resource(
                    uri_template=command.resource,
                    command=command.name,
                    name=command.tool,
                    description=capability.description,
                    toolset=command.toolset,
                )
            )
    return Offered(tools=tuple(tools), resources=tuple(resources))


def tiers(commands: Iterable[Command]) -> Mapping[Toolset, frozenset[Tier]]:
    """Return the tiers each toolset's commands are of, among those offered on ``mcp``.

    The consent page shows them beside each toolset a person may let a client use. A toolset no
    command offered on ``mcp`` is in is left out.
    """
    found: dict[Toolset, set[Tier]] = {}
    for command in commands:
        if not isinstance(command.exposure, NotExposed) and SURFACE in command.surfaces:
            found.setdefault(command.toolset, set()).add(command.capability.tier)
    ordered = sorted(found.items(), key=lambda item: TOOLSETS.index(item[0]))
    return MappingProxyType({toolset: frozenset(held) for toolset, held in ordered})
