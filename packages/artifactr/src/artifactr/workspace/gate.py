"""A gate on lattice's ``Integrations`` port, for the artifacts an integration governs (ADR-0081).

artifactr declares no integration of its own. An application names which integration governs
an artifact, by its kind and its data, and :func:`integration_gate` refuses what would make or
change one while that integration is off in the workspace.
"""

from collections.abc import Callable, Mapping

from pydantic import JsonValue

from artifactr.core import (
    Artifact,
    Command,
    CreateArtifact,
    NotEnabled,
    NotFound,
    ValidationFailed,
    Versioned,
    load_artifact,
)
from artifactr.workspace.workspace import Changes, Gate, Workspace
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
    always passes, and so does a create whose data isn't its type's, which core refuses.

    Args:
        integrations: Whether an integration is on in a tenant's workspace.
        key_of: The integration that governs an artifact, such as ``"excalidraw"`` for an
            ``excalidraw_diagram``, or None for one none does. It reads the data as core
            stores it, with its type's defaults, whether the artifact is made or changed.
    """

    async def gate(workspace: Workspace, _command: Command, changes: Changes) -> None:
        if changes is None or (data := _stored(changes)) is None:
            return
        key = key_of(changes.kind, data)
        if key is not None and not await integrations.is_enabled(
            workspace.tenant_id, workspace.workspace_id, key
        ):
            raise NotEnabled(key)

    return gate


def _stored(changes: Versioned[Artifact] | CreateArtifact) -> dict[str, JsonValue] | None:
    """The data as core stores it, or None for a create whose data isn't its type's."""
    if isinstance(changes, Versioned):
        return changes.data.to_json()
    try:
        return load_artifact(changes.kind, changes.data).to_json()
    except (NotFound, ValidationFailed):
        return None  # core refuses it, once authorize allows the command
