"""artifactr's catalog bound to its workspaces and runner: every command a client may call.

:class:`ArtifactrCatalogProvider` is lattice-core's ``Provider`` for artifactr's catalog
(lattice RFC-0014, artifactr ADR-0103). It offers each command that is exposed, but native
files', and carries each call out as artifactr's own surfaces do:

- It opens the call's workspace as the actor :func:`~artifactr.capabilities.actor_for` builds
  from the call's context, so the workspace's ``authorize``, gate and checks hear the call again
  after the enforcer's steps.
- It carries each write out through the runner's ``execute``, once per command id, so a message
  starts its thread's turn and stopping a run stops it, as on every surface. A command the
  workspace refuses raises :class:`CommandRejected`, with the refusal as the workspace gave it.
- ``artifactr.list_workspaces`` is tenant-wide (lattice ADR-0044): it lists the tenant's
  workspaces the actor may open, whatever workspace the call names. Every other command is
  called in a workspace, and refused with none.

The commands not exposed, answering a deferred call and setting the focus, are portalr's alone,
and native files' two reads are the files extra's: it offers none of them.
"""

import json
from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, JsonValue, TypeAdapter

from artifactr.agent import Runner, artifact_text, describe_outcome, list_artifacts_text
from artifactr.capabilities.provider import ActorFor, actor_for
from artifactr.commands import ARGUMENTS, ArtifactrCommands
from artifactr.commands.arguments import (
    Arguments,
    ArtifactArguments,
    CreateArguments,
    EditArguments,
    EditTextArguments,
    EventsArguments,
    FeedbackArguments,
    ListArguments,
    ModeArguments,
    NewThreadArguments,
    PageArguments,
    PostArguments,
    ProposalArguments,
    ProposeTextArguments,
    ReadThreadArguments,
    RunArguments,
)
from artifactr.core import (
    Artifact,
    Command,
    CreateArtifact,
    CreateThread,
    EditArtifact,
    FeedbackTarget,
    GiveFeedback,
    JsonPatch,
    Outcome,
    PostMessage,
    ProposeChange,
    Recorded,
    Rejection,
    RespondToProposal,
    SetThreadMode,
    StopRun,
    Watching,
    new_id,
)
from artifactr.workspace import Workspace, Workspaces
from lattice_core.capabilities import (
    CallContext,
    Capability,
    JsonObject,
    ProviderKind,
    Scope,
    ToolResult,
)
from lattice_core.commands import NotExposed

__all__ = ["FILES", "ArtifactrCatalogProvider", "CommandRejected"]

FILES: Final = frozenset({"artifactr.list_files", "artifactr.read_file"})
"""Native files' commands, which the files extra serves, not this provider."""

_TARGET: Final[TypeAdapter[FeedbackTarget]] = TypeAdapter(FeedbackTarget)


class CommandRejected(Rejection):
    """A command the workspace refused: its rejection, as artifactr's surfaces send it."""

    def __init__(self, rejection: dict[str, JsonValue]) -> None:
        super().__init__(str(rejection.get("message", "rejected")))
        self._rejection = rejection

    def payload(self) -> dict[str, JsonValue]:
        """Return the rejection as the workspace gave it."""
        return dict(self._rejection)


class ArtifactrCatalogProvider(ArtifactrCommands):
    """artifactr's catalog bound to its workspaces: lattice-core's ``Provider`` and ``Commands``.

    Args:
        workspaces: The application's workspaces, which each call opens its own in.
        runner: Carries out each write once per command id, as every surface does, so a message
            reaches the thread's agent.
        types: The artifact types a caller may create; ``artifactr.create_artifact`` names
            them and describes each one's JSON Schema, as artifactr ADR-0099's provider does.
        actor: How a call's context becomes the actor its workspace is opened as;
            :func:`~artifactr.capabilities.actor_for` if omitted.
    """

    def __init__(
        self,
        workspaces: Workspaces,
        runner: Runner[Any],
        *,
        types: Sequence[type[Artifact]],
        actor: ActorFor = actor_for,
    ) -> None:
        super().__init__()
        self.kind: ProviderKind = "command"
        self._workspaces = workspaces
        self._runner = runner
        self._actor = actor
        self._offered = tuple(
            _narrowed(command.capability, types)
            for command in self._commands
            if not isinstance(command.exposure, NotExposed) and command.name not in FILES
        )
        self._names = frozenset(capability.name for capability in self._offered)
        self._tenant_wide = frozenset(c.name for c in self._commands if c.tenant_wide)

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return the commands a client may call, the same in every workspace.

        What a workspace accepts beyond them, its types and its gate, it decides as each command
        commits.
        """
        return self._offered

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Carry out a command in the call's workspace, as the call's actor, and answer text.

        Raises:
            ValueError: If the capability isn't one this provider offers, or one called in a
                workspace names none.
            pydantic.ValidationError: If the arguments aren't the command's.
            artifactr.core.Rejection: If the workspace refuses the actor or the command;
                :class:`CommandRejected` for a write it refuses.
        """
        name = capability.name
        if name not in self._names:
            raise ValueError(f"{name} isn't a command this provider offers")
        given = ARGUMENTS[name].model_validate(arguments)
        scope, actor = context.scope, self._actor(context)
        if name in self._tenant_wide:
            assert isinstance(given, PageArguments), "listing workspaces reads a page"
            found = await self._workspaces.list(
                scope.tenant_id, actor=actor, after=given.after, limit=given.limit
            )
            return ToolResult(output="\n".join(found) or "No workspaces.")
        if scope.workspace_id is None:
            raise ValueError(f"{name} is called in a workspace, and names none")
        workspace = await self._workspaces.open(scope.tenant_id, scope.workspace_id, actor=actor)
        return ToolResult(output=await self._run(workspace, name, given))

    async def _run(self, workspace: Workspace, name: str, given: Arguments) -> str:
        """Carry out a call whose arguments are valid."""
        match given:
            case ReadThreadArguments():
                thread = await workspace.thread(given.thread_id)
                events = await workspace.read(
                    after_seq=given.after_seq, threads=[given.thread_id], limit=EVENTS
                )
                return json.dumps(
                    {
                        "thread": thread.model_dump(mode="json"),
                        "events": [envelope.model_dump(mode="json") for envelope in events],
                    }
                )
            case ModeArguments():
                command = SetThreadMode(thread_id=given.thread_id, mode=given.mode)
                await self._execute(workspace, command)
                return f"Thread {given.thread_id} is in {given.mode} mode."
            case NewThreadArguments():
                thread_id = await self._new_thread(workspace, given.title)
                return f"Started thread {thread_id}."
            case PostArguments():
                return await self._post(workspace, given)
            case RunArguments() if name == "artifactr.stop_run":
                await self._execute(workspace, StopRun(run_id=given.run_id))
                return f"Stopped run {given.run_id}."
            case RunArguments():
                return (await workspace.run(given.run_id)).model_dump_json()
            case EventsArguments():
                found = await workspace.read(after_seq=given.after_seq, limit=given.limit)
                return _lines(found) or "No events."
            case ListArguments():
                return await list_artifacts_text(workspace, given.kind)
            case CreateArguments():
                command = CreateArtifact(kind=given.kind, data=given.data)
                return describe_outcome(await self._execute(workspace, command))
            case ProposeTextArguments():
                artifact = await workspace.artifact(given.artifact_id)
                edit = artifact.edit_text(
                    given.old, given.new, field=given.field, summary=given.summary
                )
                proposal = ProposeChange(change=edit, rationale=given.rationale)
                return describe_outcome(await self._execute(workspace, proposal))
            case EditTextArguments():
                artifact = await workspace.artifact(given.artifact_id)
                edit = artifact.edit_text(
                    given.old, given.new, field=given.field, summary=given.summary
                )
                return describe_outcome(await self._execute(workspace, edit))
            case EditArguments():
                edit = EditArtifact(
                    artifact_id=given.artifact_id,
                    base_version=given.base_version,
                    patch=JsonPatch(ops=tuple(given.operations)),
                    summary=given.summary,
                )
                return describe_outcome(await self._execute(workspace, edit))
            case ArtifactArguments() if name == "artifactr.read_artifact":
                return artifact_text(
                    await workspace.artifact(given.artifact_id), as_tool_result=True
                )
            case ArtifactArguments() if name == "artifactr.list_revisions":
                return _lines(await workspace.revisions(given.artifact_id))
            case ArtifactArguments():  # artifactr.archive_artifact
                artifact = await workspace.artifact(given.artifact_id)
                return describe_outcome(await self._execute(workspace, artifact.archive()))
            case ProposalArguments():
                decision = "accept" if given.accept else "reject"
                command = RespondToProposal(
                    proposal_id=given.proposal_id, decision=decision, reason=given.reason
                )
                return describe_outcome(await self._execute(workspace, command))
            case FeedbackArguments():
                target = _TARGET.validate_python(given.target.model_dump())
                feedback = GiveFeedback(
                    feedback_type=given.feedback_type, target=target, value=given.value
                )
                await self._execute(workspace, feedback)
                return f"Recorded {given.feedback_type} feedback on the {target.kind}."
            case _ if name == "artifactr.list_proposals":
                proposals = await workspace.proposals(status="pending")
                return _lines(proposals) or "No proposals are waiting."
            case _:  # artifactr.list_threads
                return _lines(await workspace.threads()) or "There are no threads yet."

    async def _new_thread(self, workspace: Workspace, title: str | None) -> str:
        command = CreateThread(title=title or "")
        await self._execute(workspace, command)
        return command.thread_id

    async def _post(self, workspace: Workspace, given: PostArguments) -> str:
        thread_id = given.thread_id or await self._new_thread(workspace, None)
        posted = await self._execute(
            workspace, PostMessage(thread_id=thread_id, content=given.text)
        )
        run_id = posted.run_id if isinstance(posted, Recorded) else None
        if run_id is None:
            return f"Posted in thread {thread_id}; the agent already working in it will see it."
        return f"Posted in thread {thread_id}; the agent started run {run_id}."

    async def _execute(self, workspace: Workspace, command: Command | StopRun) -> Outcome:
        """Carry a command out once, under an id of its own, as every surface does.

        Raises:
            CommandRejected: If the workspace refuses it.
        """
        result = await self._runner.execute(workspace, command, command_id=new_id("cmd"))
        if result.rejection is not None:
            raise CommandRejected(result.rejection)
        outcome = result.outcome
        assert outcome is not None, "a result has an outcome or a rejection"
        assert not isinstance(outcome, Watching), "a command is never a watch"
        return outcome


EVENTS: Final = 100
"""The most of a thread's events one ``artifactr.read_thread`` returns."""


def _lines(models: Sequence[BaseModel]) -> str:
    """Models as JSON lines, one each."""
    return "\n".join(model.model_dump_json() for model in models)


def _narrowed(capability: Capability, types: Sequence[type[Artifact]]) -> Capability:
    """``artifactr.create_artifact`` names the kinds a caller may create, and describes each."""
    if capability.name != "artifactr.create_artifact":
        return capability
    described = "\n".join(
        f"- {t.kind}: {json.dumps(t.model_json_schema(), separators=(',', ':'))}" for t in types
    )
    schema = json.loads(json.dumps(capability.input_schema))
    schema["properties"]["kind"]["enum"] = [t.kind for t in types]
    description = (
        "Create an artifact of one of these kinds, whose data must match its JSON Schema:"
        f"\n{described}"
    )
    return capability.model_copy(update={"description": description, "input_schema": schema})
