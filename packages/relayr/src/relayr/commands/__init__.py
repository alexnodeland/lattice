"""relayr's commands: what a person reads of the tracker connector, declared once.

:data:`CATALOG` is relayr's static catalog, lattice-core's ``Commands`` (lattice RFC-0014,
relayr ADR-0042): the items a workspace's runs filed in its tracker, and how the connector is
doing, each a ``command`` capability named ``relayr.<name>``. relayr asks no action of its own:
each is gated by the reflexr action relayr's route asks, as reflexr's own reads would. It reads no
database and opens no workspace, so the parity test, the schema and the docs read it as it is; an
application binds it at its composition root, as portr does (lattice ADR-0041).

Rules drafted in a chat are artifactr's proposals and reflexr's stored rules, so their commands
are those packages'. relayr has no action no command gates: :data:`LISTED` is empty.
"""

from collections.abc import Iterable
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict

from lattice_core.capabilities import Capability, Gate, JsonObject
from lattice_core.commands import Command

__all__ = ["CATALOG", "LISTED", "VERSION", "RelayrCommands"]

VERSION: Final = "1.0.0"
"""Each command's version."""

RUNS = "/portalr/app/t/{tenant}/w/{workspace}/runs"
"""A workspace's runs in portalr's app, which show what they filed and the connector."""

LISTED: Final = MappingProxyType[str, str]({})
"""Each of relayr's actions that is no command's gate, and why: none, since it asks none."""


class _Nothing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _read(name: str, description: str, action: str) -> Command:
    schema: JsonObject = _Nothing.model_json_schema()
    del schema["title"]
    capability = Capability.model_validate(
        {
            "name": name,
            "version": VERSION,
            "description": description,
            "input_schema": schema,
            "output_schema": None,
            "provider": "command",
            "tier": "read",
            "effects": frozenset({"reads_private"}),
            "reversibility": "none",
            "gate": Gate(integration=None, action=action),
        }
    )
    return Command(capability=capability, toolset="automations", exposure="tool", route=RUNS)


class RelayrCommands:
    """relayr's static catalog: lattice-core's ``Commands``, with no I/O and no scope."""

    def __init__(self) -> None:
        self._commands = (
            _read(
                "relayr.list_filed_items",
                "List the items the workspace's runs filed in its tracker, each with its link and "
                "the chains that wrote to it.",
                "reflexr:read_runs",
            ),
            _read(
                "relayr.tracker_status",
                "Show how the workspace's tracker connector is doing: its binding, how far it has "
                "read the tracker, and what it couldn't publish.",
                "reflexr:read_dead_letters",
            ),
        )

    def commands(self) -> Iterable[Command]:
        """Return relayr's commands, in the order they are declared."""
        return self._commands


CATALOG: Final = RelayrCommands()
"""relayr's catalog, unbound: what an application binds at its composition root."""
