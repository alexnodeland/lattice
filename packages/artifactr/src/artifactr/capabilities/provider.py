"""artifactr's artifact tools as capabilities, each called through lattice-core's enforcement path.

:class:`ArtifactrProvider` offers the tools every artifact-aware agent has as ``command``
capabilities, named ``artifactr.<tool>``, each at version :data:`VERSION`:

- ``artifactr.list_artifacts`` and ``artifactr.read_artifact``: tier ``read``, effect
  ``reads_private``, gated by ``artifactr:read_artifacts``;
- ``artifactr.create_artifact``: tier ``write``, gated by ``artifactr:create_artifact``, made up
  for by archiving;
- ``artifactr.edit_text``: tier ``write``, gated by ``artifactr:edit_artifact``, made up for by
  a later edit;
- ``artifactr.propose_text``: tier ``write``, gated by ``artifactr:propose_change``, which
  changes nothing until a person accepts it, and so can be undone;
- ``artifactr.archive_artifact``: tier ``write``, gated by ``artifactr:archive_artifact``, and
  irreversible, since nothing unarchives.

They're for callers outside artifactr's own threads: another library's agent, a code session, a
person's outside client. Each call reaches the provider only through lattice-core's
``Enforcer``, which checks the gate, the tier, the limits, taint and approval first. The provider
then opens the call's workspace as the actor :func:`actor_for` builds from the call's context,
and commits as artifactr's own tools do, so the workspace's ``authorize``, gate and checks hear
each command again. A change is attributed to that actor, in no thread.

None of them declares an approval of its own: whether a call needs one is the application's
``ApprovalPolicy``'s, asked by the enforcer, which pauses an agent's run the way a tool's
``requires_approval`` does (artifactr ADR-0099).
"""

import json
from collections.abc import Callable, Sequence
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from artifactr.agent import artifact_text, describe_outcome, list_artifacts_text, submit
from artifactr.core import Artifact, CreateArtifact, ExternalAgentActor, UserActor
from artifactr.workspace import Workspace, Workspaces
from lattice_core.capabilities import (
    CallContext,
    Capability,
    Gate,
    JsonObject,
    PersonCaller,
    ProviderKind,
    RunCaller,
    Scope,
    ToolResult,
)

__all__ = ["NAMES", "VERSION", "ActorFor", "ArtifactrProvider", "actor_for"]

VERSION: Final = "1.0.0"
"""Each capability's version."""

NAMES: Final = (
    "artifactr.list_artifacts",
    "artifactr.read_artifact",
    "artifactr.create_artifact",
    "artifactr.edit_text",
    "artifactr.propose_text",
    "artifactr.archive_artifact",
)
"""The capabilities' names, in the order they're offered."""

type ActorFor = Callable[[CallContext], UserActor | ExternalAgentActor]
"""How a call's context becomes the actor its workspace is opened as."""

_OUTPUT: Final[JsonObject] = {"type": "string"}
"""Every capability answers with text for a model, as artifactr's own tools do."""


def actor_for(context: CallContext) -> UserActor | ExternalAgentActor:
    """Return the actor a call acts as: the outside client it came through, or else its caller.

    - A call through an outside client (``via``) is that client's
      :class:`~artifactr.core.ExternalAgentActor`, by its connection's id and name, for the
      person the caller is or acts for (lattice RFC-0014).
    - A person's own call is their :class:`~artifactr.core.UserActor`.
    - An agent's run is an outside agent's, ``agent:<agent>``, and a code session's is
      ``session:<id>``, each for the person it acts for, if it acts for one. Neither is
      artifactr's own thread agent.

    Args:
        context: The call's context.
    """
    caller = context.caller
    person_id = caller.id if isinstance(caller, PersonCaller) else caller.on_behalf_of
    person = None if person_id is None else UserActor(id=person_id)
    if context.via is not None:
        via = context.via
        return ExternalAgentActor(
            client_id=via.connection_id, name=via.client_name, on_behalf_of=person
        )
    if isinstance(caller, PersonCaller):
        return UserActor(id=caller.id)
    if isinstance(caller, RunCaller):
        return ExternalAgentActor(
            client_id=f"agent:{caller.agent}", name=caller.agent, on_behalf_of=person
        )
    return ExternalAgentActor(
        client_id=f"session:{caller.id}", name="code session", on_behalf_of=person
    )


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class _List(_Arguments):
    kind: str | None = None
    """Only list artifacts of this kind."""


class _Read(_Arguments):
    artifact_id: str
    """The artifact to read."""


class _Create(_Arguments):
    kind: str
    """The kind of artifact to create."""
    data: dict[str, Any]
    """Its data, which must match its kind's JSON Schema."""


class _EditText(_Arguments):
    artifact_id: str
    """The artifact to edit."""
    old: str
    """Text that occurs exactly once in the field now. Include enough context to make it unique.
    Use an empty string only to write into an empty field."""
    new: str
    """The replacement text."""
    field: str = "text"
    """The text field to edit."""
    summary: str | None = None
    """A short description of the change, shown to others."""


class _ProposeText(_EditText):
    rationale: str | None = None
    """Why you propose it, shown to the person who reviews it."""


class _Archive(_Arguments):
    artifact_id: str
    """The artifact to archive."""


type _Given = _List | _Read | _Create | _EditText | _ProposeText | _Archive

_ARGUMENTS: Final[dict[str, type[_Given]]] = dict(
    zip(NAMES, (_List, _Read, _Create, _EditText, _ProposeText, _Archive), strict=True)
)


def _schema(arguments: type[_Arguments]) -> dict[str, Any]:
    schema = arguments.model_json_schema()
    del schema["title"]
    return schema


def _capabilities(types: Sequence[type[Artifact]]) -> tuple[Capability, ...]:
    kinds = [t.kind for t in types]
    described = "\n".join(
        f"- {t.kind}: {json.dumps(t.model_json_schema(), separators=(',', ':'))}" for t in types
    )
    create = _schema(_Create)
    create["properties"]["kind"]["enum"] = kinds
    reading = frozenset({"reads_private"})
    rows: tuple[tuple[str, str, str, frozenset[str], str], ...] = (
        (
            "List the artifacts in the workspace, optionally of one kind, one per line.",
            "read",
            "artifactr:read_artifacts",
            reading,
            "none",
        ),
        (
            "Read an artifact's current version.",
            "read",
            "artifactr:read_artifacts",
            reading,
            "none",
        ),
        (
            "Create an artifact of one of these kinds, whose data must match its JSON Schema:"
            f"\n{described}",
            "write",
            "artifactr:create_artifact",
            frozenset(),
            "compensable",
        ),
        (
            "Replace one exact passage of an artifact's text field.",
            "write",
            "artifactr:edit_artifact",
            frozenset(),
            "compensable",
        ),
        (
            "Propose replacing one exact passage of an artifact's text field, for a person to "
            "accept or reject. Nothing changes until they accept it.",
            "write",
            "artifactr:propose_change",
            frozenset(),
            "undoable",
        ),
        (
            "Archive an artifact that is no longer needed. It stays readable, and can't be "
            "unarchived.",
            "write",
            "artifactr:archive_artifact",
            frozenset(),
            "irreversible",
        ),
    )
    schemas = {name: _schema(arguments) for name, arguments in _ARGUMENTS.items()}
    schemas["artifactr.create_artifact"] = create
    return tuple(
        Capability.model_validate(
            {
                "name": name,
                "version": VERSION,
                "description": description,
                "input_schema": schemas[name],
                "output_schema": _OUTPUT,
                "provider": "command",
                "tier": tier,
                "effects": effects,
                "reversibility": reversibility,
                "gate": Gate(integration=None, action=action),
            }
        )
        for name, (description, tier, action, effects, reversibility) in zip(
            NAMES, rows, strict=True
        )
    )


class ArtifactrProvider:
    """artifactr's artifact tools, as capabilities, offered in every workspace.

    Args:
        workspaces: The application's workspaces, which each call opens its own in.
        types: The artifact types a caller may create; their JSON Schemas are described once,
            in ``artifactr.create_artifact``'s description.
        actor: How a call's context becomes the actor its workspace is opened as;
            :func:`actor_for` if omitted.
    """

    def __init__(
        self,
        workspaces: Workspaces,
        *,
        types: Sequence[type[Artifact]],
        actor: ActorFor = actor_for,
    ) -> None:
        self.kind: ProviderKind = "command"
        self._workspaces = workspaces
        self._actor = actor
        self._capabilities = _capabilities(types)

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return the capabilities, which are the same in every workspace.

        What a workspace accepts beyond them, its types and its gate, it decides as each command
        commits.
        """
        return self._capabilities

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Call one of the capabilities in the call's workspace, as the call's actor.

        Raises:
            ValueError: If the capability isn't one of artifactr's.
            pydantic.ValidationError: If the arguments aren't the capability's.
            artifactr.core.Rejection: If the workspace refuses the call or its command.
        """
        if capability.name not in _ARGUMENTS:
            raise ValueError(f"{capability.name} isn't one of artifactr's capabilities")
        given = _ARGUMENTS[capability.name].model_validate(arguments)
        scope = context.scope
        workspace = await self._workspaces.open(
            scope.tenant_id, scope.workspace_id, actor=self._actor(context)
        )
        return ToolResult(output=await _run(workspace, given))


async def _run(workspace: Workspace, given: _Given) -> str:
    """Carry out a call whose arguments are valid, as artifactr's own tools do, in no thread."""
    match given:
        case _List():
            return await list_artifacts_text(workspace, given.kind)
        case _Read():
            return artifact_text(await workspace.artifact(given.artifact_id))
        case _Create():
            command = CreateArtifact(kind=given.kind, data=given.data)
            return describe_outcome(await workspace.commit(command))
        case _ProposeText():
            artifact = await workspace.artifact(given.artifact_id)
            edit = artifact.edit_text(
                given.old, given.new, field=given.field, summary=given.summary
            )
            outcome = await submit(workspace, edit, propose=True, rationale=given.rationale)
            return describe_outcome(outcome)
        case _EditText():
            artifact = await workspace.artifact(given.artifact_id)
            edit = artifact.edit_text(
                given.old, given.new, field=given.field, summary=given.summary
            )
            return describe_outcome(await workspace.commit(edit))
        case _:  # archive
            artifact = await workspace.artifact(given.artifact_id)
            return describe_outcome(await workspace.commit(artifact.archive()))
