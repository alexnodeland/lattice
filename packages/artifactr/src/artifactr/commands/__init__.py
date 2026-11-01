"""artifactr's commands: every action a person takes on threads and artifacts, declared once.

:data:`CATALOG` is artifactr's static catalog, lattice-core's ``Commands`` (lattice RFC-0014,
artifactr ADR-0100): workspaces, threads, messages, runs, artifacts, revisions, proposals,
feedback, deferred answers and files' reads, each a ``command`` capability named
``artifactr.<name>``, gated by the grantr action artifactr's workspace asks for it. It reads no
database and opens no workspace, so the parity test, the schema and the docs read it as it is;
an application binds it at its composition root, as portr does (lattice ADR-0041).

- **Not exposed, portalr's alone:** answering a deferred tool's call, which a person answers
  in portalr or by elicitation, never a model; and setting the focus, which is what a person has
  open in portalr.
- **No command, by action** (:data:`LISTED`): what the application's own machinery does
  (claiming threads, keeping cursors, recording a run, a model's calls), ``artifactr:open``,
  asked before every command in a workspace, and connected apps' code and native files' making,
  which come in 0.3.x (#924), each with its reason.

The names of the tools artifactr's provider already offers (artifactr ADR-0099) are these
commands' names, so a client sees one tool for each.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from lattice_core.capabilities import Capability, Effect, Gate, JsonObject, Reversibility, Tier
from lattice_core.commands import Command, Exposure, NotExposed, Surface, Toolset

__all__ = ["CATALOG", "LISTED", "VERSION", "ArtifactrCommands"]

VERSION: Final = "1.0.0"
"""Each command's version."""

APP = "/portalr/app/t/{tenant}"
"""portalr's app, for a tenant: where each command's route starts."""

HERE = f"{APP}/w/{{workspace}}"
"""A workspace in portalr's app."""

LISTED: Final = MappingProxyType(
    {
        "artifactr:open": "asked before every command in a workspace, never on its own",
        "artifactr:claim_thread": "the runner's own bookkeeping: claiming a thread's turn",
        "artifactr:save_cursor": "the log's consumers' bookkeeping",
        "artifactr:read_cursors": "the log's consumers' bookkeeping",
        "artifactr:record": "a run's own steps, recorded by the runner",
        "artifactr:use_model": "a run's model calls, made by the runner",
        "artifactr:create_native_file": "native files' making and check-out come in 0.3.x (#924)",
        "artifactr:run_connected_code": "connected apps' commands come in 0.3.x (#924)",
    }
)
"""Each of artifactr's actions that is no command's gate, and why: what the parity test reads."""


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class _Page(_Arguments):
    after: str | None = None
    """Read after this id, from the last page."""
    limit: int = Field(default=100, ge=1, le=500)
    """How many to read."""


class _Nothing(_Arguments):
    pass


class _Thread(_Arguments):
    thread_id: str
    """The thread."""


class _ReadThread(_Thread):
    after_seq: int = Field(default=0, ge=0)
    """Read the thread's events after this sequence number, to read what came since."""


class _NewThread(_Arguments):
    title: str | None = None
    """Its title; one is made from its first message if omitted."""


class _Post(_Arguments):
    text: str = Field(min_length=1)
    """The message."""
    thread_id: str | None = None
    """The thread to post in; a new one is started if omitted."""


class _Run(_Arguments):
    run_id: str
    """The run."""


class _Events(_Arguments):
    after_seq: int = Field(default=0, ge=0)
    """Read the workspace's events after this sequence number."""
    limit: int = Field(default=100, ge=1, le=1000)
    """How many to read."""


class _List(_Arguments):
    kind: str | None = None
    """Only list artifacts of this kind."""


class _Artifact(_Arguments):
    artifact_id: str
    """The artifact."""


class _Create(_Arguments):
    kind: str
    """The kind of artifact to create: one the application registers."""
    data: dict[str, Any]
    """Its data, which must match its kind's JSON Schema."""


class _EditText(_Artifact):
    old: str
    """Text that occurs exactly once in the field now; an empty string writes an empty field."""
    new: str
    """The replacement text."""
    field: str = "text"
    """The text field to edit."""
    summary: str | None = None
    """A short description of the change, shown to others."""


class _ProposeText(_EditText):
    rationale: str | None = None
    """Why you propose it, shown to the person who reviews it."""


class _Edit(_Artifact):
    operations: list[dict[str, Any]] = Field(min_length=1)
    """JSON Patch operations on the artifact's data."""
    summary: str | None = None
    """A short description of the change, shown to others."""


class _Proposal(_Arguments):
    proposal_id: str
    """The proposal."""
    accept: bool
    """Whether to accept it, applying its change, or reject it."""
    reason: str | None = None
    """Why, shown to whoever proposed it."""


class _Feedback(_Arguments):
    target_id: str
    """The message, run or artifact the feedback is on."""
    rating: int = Field(ge=-1, le=1)
    """-1, 0 or 1."""
    comment: str | None = None
    """What you would say about it."""


class _Deferred(_Arguments):
    call_id: str
    """The deferred call."""
    approved: bool
    """Whether to let it go ahead."""


class _Focus(_Arguments):
    artifact_id: str | None
    """What is open; none if omitted."""


class _Mode(_Thread):
    mode: str
    """The thread's mode, as its runner offers them."""


class _File(_Artifact):
    page: int = Field(default=1, ge=1)
    """The page to read, of a file read a page at a time."""


@dataclass(frozen=True)
class _Spec:
    name: str
    description: str
    action: str
    arguments: type[_Arguments]
    tier: Tier = "write"
    reversibility: Reversibility = "compensable"
    effects: frozenset[Effect] = frozenset()
    toolset: Toolset = "core"
    exposure: Exposure | NotExposed = "tool"
    route: str | None = None
    resource: str | None = None
    surfaces: frozenset[Surface] = field(
        default_factory=lambda: frozenset[Surface]({"portalr", "mcp", "acp", "webmcp"})
    )


def _read(
    name: str, description: str, action: str, arguments: type[_Arguments], **more: Any
) -> _Spec:
    return _Spec(
        name,
        description,
        action,
        arguments,
        tier="read",
        reversibility="none",
        effects=frozenset({"reads_private"}),
        **more,
    )


_SPECS: Final[tuple[_Spec, ...]] = (
    _read(
        "artifactr.list_workspaces",
        "List the workspaces you can open in the tenant, a page at a time.",
        "artifactr:read_workspaces",
        _Page,
        route=APP,
    ),
    _read(
        "artifactr.list_threads",
        "List the workspace's threads you can open, newest first.",
        "artifactr:read_threads",
        _Nothing,
        route=HERE,
    ),
    _read(
        "artifactr.read_thread",
        "Read a thread's messages and runs, or what came since a sequence number.",
        "artifactr:read_threads",
        _ReadThread,
        exposure="both",
        route=f"{HERE}/threads/{{thread_id}}",
        resource="artifactr://{tenant}/{workspace}/threads/{thread_id}",
    ),
    _Spec(
        "artifactr.create_thread",
        "Start an empty thread in the workspace.",
        "artifactr:create_thread",
        _NewThread,
        route=f"{HERE}/threads/{{thread_id}}",
    ),
    _Spec(
        "artifactr.post_message",
        "Post a message in a thread, or start one with it; the thread's agent answers it.",
        "artifactr:post_message",
        _Post,
        reversibility="irreversible",
        route=f"{HERE}/threads/{{thread_id}}",
    ),
    _read(
        "artifactr.read_run",
        "Read a run as it stands: its status, steps and outcome.",
        "artifactr:read_runs",
        _Run,
        route=f"{HERE}/runs",
    ),
    _Spec(
        "artifactr.stop_run",
        "Stop a run that is going; what it did stays done.",
        "artifactr:stop_run",
        _Run,
        reversibility="irreversible",
        route=f"{HERE}/runs",
    ),
    _read(
        "artifactr.read_events",
        "Read the workspace's events after a sequence number, oldest first.",
        "artifactr:read_events",
        _Events,
        toolset="automations",
        route=None,
    ),
    _read(
        "artifactr.list_artifacts",
        "List the artifacts in the workspace, optionally of one kind, one per line.",
        "artifactr:read_artifacts",
        _List,
        route=f"{HERE}/artifacts",
    ),
    _read(
        "artifactr.read_artifact",
        "Read an artifact's current version.",
        "artifactr:read_artifacts",
        _Artifact,
        exposure="both",
        route=f"{HERE}/artifacts/{{artifact_id}}",
        resource="artifactr://{tenant}/{workspace}/artifacts/{artifact_id}",
    ),
    _read(
        "artifactr.list_revisions",
        "List an artifact's revisions, oldest first, with who made each and why.",
        "artifactr:read_history",
        _Artifact,
        route=f"{HERE}/artifacts/{{artifact_id}}",
    ),
    _Spec(
        "artifactr.create_artifact",
        "Create an artifact of a kind the workspace has, whose data must match its JSON Schema.",
        "artifactr:create_artifact",
        _Create,
        route=f"{HERE}/artifacts/{{artifact_id}}",
    ),
    _Spec(
        "artifactr.edit_text",
        "Replace one exact passage of an artifact's text field.",
        "artifactr:edit_artifact",
        _EditText,
        route=f"{HERE}/artifacts/{{artifact_id}}",
    ),
    _Spec(
        "artifactr.edit_artifact",
        "Change an artifact's data with JSON Patch operations.",
        "artifactr:edit_artifact",
        _Edit,
        route=f"{HERE}/artifacts/{{artifact_id}}",
    ),
    _Spec(
        "artifactr.propose_text",
        "Propose replacing one exact passage of an artifact's text field, for a person to "
        "accept or reject. Nothing changes until they accept it.",
        "artifactr:propose_change",
        _ProposeText,
        reversibility="undoable",
        route=f"{HERE}/proposals",
    ),
    _Spec(
        "artifactr.archive_artifact",
        "Archive an artifact that is no longer needed. It stays readable, and can't be unarchived.",
        "artifactr:archive_artifact",
        _Artifact,
        reversibility="irreversible",
        route=f"{HERE}/artifacts/{{artifact_id}}",
    ),
    _read(
        "artifactr.list_proposals",
        "List the workspace's proposals waiting for an answer.",
        "artifactr:read_proposals",
        _Nothing,
        route=f"{HERE}/proposals",
    ),
    _Spec(
        "artifactr.respond_to_proposal",
        "Accept a proposal, applying its change, or reject it.",
        "artifactr:respond_to_proposal",
        _Proposal,
        route=f"{HERE}/proposals",
    ),
    _Spec(
        "artifactr.give_feedback",
        "Rate a message, run or artifact, with a comment if you have one.",
        "artifactr:give_feedback",
        _Feedback,
        toolset="feedback",
        route=None,
    ),
    _Spec(
        "artifactr.answer_deferred",
        "Answer a deferred tool's call.",
        "artifactr:answer_deferred",
        _Deferred,
        exposure=NotExposed(reason="a deferred call is answered by a person, never a model"),
        route=f"{HERE}/threads/{{thread_id}}",
        surfaces=frozenset({"portalr"}),
    ),
    _Spec(
        "artifactr.set_focus",
        "Set what is open beside a thread.",
        "artifactr:set_focus",
        _Focus,
        exposure=NotExposed(reason="the focus is what a person has open in portalr"),
        route=f"{HERE}/threads/{{thread_id}}",
        surfaces=frozenset({"portalr"}),
    ),
    _Spec(
        "artifactr.set_thread_mode",
        "Set a thread's mode, which says how its agent acts on artifacts.",
        "artifactr:set_thread_mode",
        _Mode,
        route=f"{HERE}/threads/{{thread_id}}",
    ),
    _read(
        "artifactr.list_files",
        "List the workspace's native files.",
        "artifactr:read_artifacts",
        _Nothing,
        route=f"{HERE}/artifacts",
    ),
    _read(
        "artifactr.read_file",
        "Read a native file's text, a page at a time.",
        "artifactr:read_artifacts",
        _File,
        route=f"{HERE}/artifacts/{{artifact_id}}",
    ),
)


def _schema(arguments: type[_Arguments]) -> JsonObject:
    schema: JsonObject = arguments.model_json_schema()
    del schema["title"]
    return schema


def _command(spec: _Spec) -> Command:
    capability = Capability.model_validate(
        {
            "name": spec.name,
            "version": VERSION,
            "description": spec.description,
            "input_schema": _schema(spec.arguments),
            "output_schema": None,
            "provider": "command",
            "tier": spec.tier,
            "effects": spec.effects,
            "reversibility": spec.reversibility,
            "gate": Gate(integration=None, action=spec.action),
        }
    )
    return Command(
        capability=capability,
        toolset=spec.toolset,
        exposure=spec.exposure,
        route=spec.route,
        resource=spec.resource,
        surfaces=spec.surfaces,
    )


class ArtifactrCommands:
    """artifactr's static catalog: lattice-core's ``Commands``, with no I/O and no scope."""

    def __init__(self) -> None:
        self._commands = tuple(_command(spec) for spec in _SPECS)

    def commands(self) -> Iterable[Command]:
        """Return artifactr's commands, in the order they are declared."""
        return self._commands


CATALOG: Final = ArtifactrCommands()
"""artifactr's catalog, unbound: what an application binds at its composition root."""
