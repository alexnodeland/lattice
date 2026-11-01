"""Native files' commands, bound to the workspaces and native files: the files extra's provider.

:class:`NativeFilesProvider` is lattice-core's ``Provider`` for the two commands of artifactr's
catalog that need the files extra, ``artifactr.list_files`` and ``artifactr.read_file``
(lattice RFC-0014, artifactr ADR-0104). An application binds it beside
:class:`artifactr.capabilities.ArtifactrCatalogProvider`, which serves the rest of the catalog
and none of these, so the two never offer a name twice.

It opens the call's workspace as :func:`artifactr.capabilities.actor_for`'s actor, so the
workspace's ``authorize`` and hidden artifacts hold for each read, and reads the words the
file's app read from it, as kept, through :class:`~artifactr.files.native.NativeFiles`, as the
files router's text does.
"""

import json
from typing import Final

from artifactr.capabilities import FILES, ActorFor, actor_for
from artifactr.commands import ARGUMENTS, CATALOG
from artifactr.commands.arguments import FileArguments
from artifactr.files.manifest import NativeFile
from artifactr.files.native import NativeFiles
from artifactr.workspace import Workspace, Workspaces
from lattice_core.capabilities import (
    CallContext,
    Capability,
    JsonObject,
    ProviderKind,
    Scope,
    ToolResult,
)

__all__ = ["PAGE_CHARS", "NativeFilesProvider"]

PAGE_CHARS: Final = 8_000
"""How many of a file's characters one page of ``artifactr.read_file`` holds."""


class NativeFilesProvider:
    """Native files' commands, lattice-core's ``Provider``: listing them and reading their words.

    Args:
        workspaces: The application's workspaces, which each call opens its own in.
        files: The application's native files, which read a file's words.
        actor: How a call's context becomes the actor its workspace is opened as;
            :func:`artifactr.capabilities.actor_for` if omitted.
    """

    def __init__(
        self, workspaces: Workspaces, files: NativeFiles, *, actor: ActorFor = actor_for
    ) -> None:
        self.kind: ProviderKind = "command"
        self._workspaces = workspaces
        self._files = files
        self._actor = actor
        self._offered = tuple(
            command.capability for command in CATALOG.commands() if command.name in FILES
        )

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return native files' two commands, the same in every workspace."""
        return self._offered

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """List the workspace's native files, or read a page of one's words, as the call's actor.

        Raises:
            ValueError: If the capability isn't one of native files' commands, or the call names
                no workspace.
            pydantic.ValidationError: If the arguments aren't the command's.
            artifactr.core.Rejection: If the workspace refuses the read, or has no such file.
        """
        name = capability.name
        if name not in FILES:
            raise ValueError(f"{name} isn't one of native files' commands")
        given = ARGUMENTS[name].model_validate(arguments)
        scope = context.scope
        if scope.workspace_id is None:
            raise ValueError(f"{name} is called in a workspace, and names none")
        workspace = await self._workspaces.open(
            scope.tenant_id, scope.workspace_id, actor=self._actor(context)
        )
        if isinstance(given, FileArguments):
            return ToolResult(output=await self._page(workspace, given))
        return ToolResult(output=await _listed(workspace))

    async def _page(self, workspace: Workspace, given: FileArguments) -> str:
        words = (await self._files.read(workspace, given.artifact_id, part="text")).decode()
        pages = max(1, -(-len(words) // PAGE_CHARS))
        if given.page > pages:
            return (
                f"{given.artifact_id} has {pages} page(s) of text; there is no page {given.page}."
            )
        start = (given.page - 1) * PAGE_CHARS
        page = words[start : start + PAGE_CHARS]
        more = f"\n\n[page {given.page} of {pages}]" if pages > 1 else ""
        return page + more


async def _listed(workspace: Workspace) -> str:
    """The workspace's native files, one JSON line each, or a sentence if it has none."""
    found = await workspace.artifacts(NativeFile)
    lines = [
        json.dumps(
            {
                "artifact_id": head.id,
                "version": head.version,
                "kind": head.data.kind,
                "name": head.data.name,
                "media_type": head.data.content.media_type,
                "size": head.data.content.size,
                "pages": head.data.pages,
            }
        )
        for head in found
    ]
    return "\n".join(lines) or "There are no native files here."
