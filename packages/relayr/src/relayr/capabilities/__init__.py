"""relayr's catalog bound to its tracker connector and reflexr's workspaces: its provider.

:class:`RelayrProvider` is lattice-core's ``Provider`` and ``Commands`` for relayr's two reads
(lattice RFC-0014, relayr ADR-0043): what a workspace's runs filed in its tracker, and how its
connector is doing. Each call opens the call's reflexr workspace as the actor reflexr's
provider would, asks its ``authorize`` for the reflexr action the command's gate names, as
relayr's routes do, and answers what they answer, as JSON.
"""

from collections.abc import Callable
from typing import Final

from pydantic import BaseModel, ConfigDict

from lattice_core.capabilities import (
    CallContext,
    Capability,
    JsonObject,
    ProviderKind,
    Scope,
    ToolResult,
)
from reflexr.commands import actor_for
from reflexr.core import ExternalAgentActor, UserActor
from reflexr.workspace import Access, Workspaces
from relayr.commands import RelayrCommands
from relayr.ledger import WorkspaceKey
from relayr.trackers import Trackers, filed_in, following_in

__all__ = ["FILED", "STATUS", "RelayrProvider"]

FILED: Final = "relayr.list_filed_items"
"""The command that lists what a workspace's runs filed."""

STATUS: Final = "relayr.tracker_status"
"""The command that says how a workspace's connector is doing."""


class _NoArguments(BaseModel):
    """Neither command takes an argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RelayrProvider(RelayrCommands):
    """relayr's catalog bound to its connector: lattice-core's ``Provider`` and ``Commands``.

    Args:
        trackers: The tracker connector, whose ledger, bindings and adapters are read.
        workspaces: reflexr's workspaces, whose ``authorize`` decides each read.
        actor: How a call's context becomes the actor its workspace is opened as; reflexr's
            provider's, if omitted.
    """

    def __init__(
        self,
        trackers: Trackers,
        workspaces: Workspaces,
        *,
        actor: Callable[[CallContext], UserActor | ExternalAgentActor] = actor_for,
    ) -> None:
        super().__init__()
        self.kind: ProviderKind = "command"
        self._trackers = trackers
        self._workspaces = workspaces
        self._actor = actor
        self._offered = tuple(command.capability for command in self._commands)

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return relayr's two reads, the same in every workspace."""
        return self._offered

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Read what the workspace's runs filed, or how its connector is doing, as JSON.

        Raises:
            ValueError: If the capability isn't one of relayr's, or the call names no workspace.
            pydantic.ValidationError: If it is given an argument.
            reflexr.core.Rejection: If the workspace refuses the actor or the read.
        """
        name = capability.name
        if name not in (FILED, STATUS):
            raise ValueError(f"{name} isn't one of relayr's commands")
        _NoArguments.model_validate(arguments)
        scope = context.scope
        if scope.workspace_id is None:
            raise ValueError(f"{name} is called in a workspace, and names none")
        workspace = await self._workspaces.open(
            scope.tenant_id, scope.workspace_id, actor=self._actor(context)
        )
        await workspace.check(Access(action=capability.gate.action))
        key = WorkspaceKey(scope.tenant_id, scope.workspace_id)
        read = await (filed_in if name == FILED else following_in)(self._trackers, key)
        return ToolResult(output=read.model_dump_json())
