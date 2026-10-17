"""A gate on lattice's ``Integrations`` port, for the artifacts an integration governs (ADR-0081).

artifactr declares no integration of its own. An application names which integration governs
an artifact, by its kind and its data, and :func:`integration_gate` refuses what would change
one while that integration is off in the workspace.
"""

from collections.abc import Callable, Mapping

from pydantic import JsonValue

from artifactr.core import (
    Artifact,
    Command,
    CreateArtifact,
    EditArtifact,
    NotEnabled,
    ProposeChange,
    RespondToProposal,
    Versioned,
)
from artifactr.workspace.workspace import Gate, Workspace
from lattice_core.integrations import Integrations

KeyOf = Callable[[str, Mapping[str, JsonValue]], str | None]
"""The integration that governs an artifact, by its kind and its data as JSON, or None."""


def integration_gate(integrations: Integrations, key_of: KeyOf) -> Gate:
    """Return a gate that refuses changes to what an integration governs while it is off.

    While it is off, creating, editing and proposing to create or edit such an artifact are
    refused, and so is accepting a proposal about one, whatever it proposes, since accepting
    carries a change out. Archiving one, proposing to archive one, and rejecting a proposal
    pass, so people can still tidy up; a pending proposal stays, to be accepted once the
    integration is on again. A command on no artifact, or on one no integration governs,
    always passes.

    Args:
        integrations: Whether an integration is on in a tenant's workspace.
        key_of: The integration that governs an artifact, such as ``"excalidraw"`` for an
            ``excalidraw_diagram``, or None for one none does.
    """

    async def gate(
        workspace: Workspace, command: Command, changes: Versioned[Artifact] | CreateArtifact | None
    ) -> None:
        if changes is None or not _changes_data(command):
            return
        if isinstance(changes, CreateArtifact):
            data = changes.data
        else:
            data = changes.data.model_dump(mode="json")
        key = key_of(changes.kind, data)
        if key is not None and not await integrations.is_enabled(
            workspace.tenant_id, workspace.workspace_id, key
        ):
            raise NotEnabled(key)

    return gate


def _changes_data(command: Command) -> bool:
    """Whether a command makes or changes an artifact's data, or accepts a proposal that may."""
    match command:
        case CreateArtifact() | EditArtifact():
            return True
        case ProposeChange(change=change):
            return _changes_data(change)
        case RespondToProposal(decision=decision):
            return decision == "accept"
        case _:
            return False
