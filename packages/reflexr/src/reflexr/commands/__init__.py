"""reflexr's commands: every action a person takes on events, rules and runs, declared once.

:data:`CATALOG` is reflexr's static catalog, lattice-core's ``Commands`` (lattice RFC-0014,
reflexr ADR-0067): publishing and reading events, the rules (registered in code and stored),
their status, history and replay, schedules, runs (retry, skip, cancel), dead letters and
feedback, each a ``command`` capability named ``reflexr.<name>``, gated by the grantr action
reflexr's workspace asks for it. It reads no database and opens no workspace, so the parity test,
the schema and the docs read it as it is; an application binds it at its composition root, as
portr does (lattice ADR-0041).

- **The names are the tools reflexr's own MCP server serves,** so a client that moves from it to
  portr sees the same tools. Each is in the ``automations`` toolset, but feedback, in ``feedback``.
- **A run is a resource too,** by ``reflexr://{tenant}/{workspace}/runs/{run_id}``, the URI
  reflexr's server already serves.
- **No command, by action** (:data:`LISTED`): ``reflexr:open``, asked before every command in a
  workspace, and what a run and the log's consumers do as they go, each with its reason.

:func:`provider` binds the catalog to the application's ``Workspaces`` (reflexr ADR-0068):
lattice-core's ``Provider``, whose ``call`` opens the call's workspace as the call's actor
(:func:`actor_for`) and runs the command as reflexr's own surfaces do, so the workspace checks it
again. Each answers JSON text.
"""

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from lattice_core.capabilities import (
    CallContext,
    Capability,
    Effect,
    Gate,
    JsonObject,
    PersonCaller,
    ProviderKind,
    Reversibility,
    RunCaller,
    Scope,
    Tier,
    ToolResult,
)
from lattice_core.commands import Command, Exposure, NotExposed, Surface, Toolset
from reflexr.core import (
    ArchiveRule,
    CancelRun,
    ExternalAgentActor,
    FeedbackTarget,
    GiveFeedback,
    InstallRule,
    Publish,
    Rejection,
    ReplayRule,
    RetryRun,
    Rule,
    RunStatus,
    SkipRun,
    UpdateRule,
    UserActor,
    load_event,
    new_id,
)
from reflexr.core import Command as Frame
from reflexr.core import scope_key as key_of
from reflexr.workspace import Workspace, Workspaces

__all__ = [
    "CATALOG",
    "LISTED",
    "VERSION",
    "CommandRejected",
    "ReflexrCommands",
    "ReflexrProvider",
    "actor_for",
    "provider",
]

VERSION: Final = "1.0.0"
"""Each command's version."""

HERE = "/portalr/app/t/{tenant}/w/{workspace}"
"""A workspace in portalr's app: where each command's route starts."""

RUNS = f"{HERE}/runs"
"""The workspace's runs in portalr's app."""

RULES = f"{HERE}/rules"
"""The workspace's rules and schedules in portalr's app."""

RULE = f"{RULES}/{{rule}}"
"""One rule in portalr's app."""

LISTED: Final = MappingProxyType(
    {
        "reflexr:open": "asked before every command in a workspace, never on its own",
        "reflexr:checkpoint_run": "a run's own progress, recorded by the action as it runs",
        "reflexr:save_cursor": "the log's consumers' bookkeeping",
        "reflexr:read_cursors": "the log's consumers' bookkeeping; a rule's shows in its status",
    }
)
"""Each of reflexr's actions that is no command's gate, and why: what the parity test reads."""


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class _Nothing(_Arguments):
    pass


class _Publish(_Arguments):
    event: dict[str, Any]
    """The event: an object with its ``type`` and its fields."""
    id: str | None = None
    """Its id; publishing an id already in the log adds nothing. One is made if omitted."""
    correlation_id: str | None = None
    """The causal chain it joins, which the event that started it named."""


class _Events(_Arguments):
    after_seq: int = Field(default=0, ge=0)
    """Read the log after this sequence number."""
    before_seq: int | None = Field(default=None, ge=1)
    """Read the log before this sequence number, to read back through it."""
    types: list[str] | None = None
    """Read only events of these types."""
    limit: int | None = Field(default=None, ge=1, le=1000)
    """Read the window's first envelopes, this many; the first 50 if neither this nor ``last``."""
    last: int | None = Field(default=None, ge=1, le=1000)
    """Read the window's last envelopes, this many."""


class _Rule(_Arguments):
    rule: str
    """The rule's name, such as ``oncall:triage``."""


class _Replay(_Rule):
    from_seq: int = Field(default=0, ge=0)
    """Evaluate the rule again from this sequence number."""
    mode: Literal["rebuild", "refire"] = "rebuild"
    """``rebuild`` its state quietly, or ``refire`` its actions."""


class _Install(_Arguments):
    rule: Rule
    """The rule to store: version 1, or the next of an archived rule of its name."""
    provenance: dict[str, Any] | None = None
    """Where the rule came from, such as the artifact a person accepted: kept, not read."""


class _Update(_Install):
    expected_version: int | None = Field(default=None, ge=1)
    """The version you last saw, so a change someone made first is refused, not overwritten."""


class _Archive(_Rule):
    expected_version: int | None = Field(default=None, ge=1)
    """The version you last saw, so a change someone made first is refused, not overwritten."""
    reason: str | None = None
    """Why, kept with the change."""


class _Runs(_Arguments):
    rule: str | None = None
    """Only runs of this rule."""
    scope_key: list[JsonValue] | None = None
    """Only runs of this scope, its values in order, as a run's ``scope_key`` holds them."""
    status: RunStatus | None = None
    """Only runs in this status."""
    limit: int = Field(default=20, ge=1, le=1000)
    """How many to list, newest first."""


class _Run(_Arguments):
    run_id: str
    """The run."""


class _Settle(_Run):
    reason: str | None = None
    """Why, kept with the run."""


class _DeadLetters(_Arguments):
    rule: str | None = None
    """Only those of this rule."""


class _Feedback(_Arguments):
    feedback_type: str
    """A feedback type the application registers."""
    target: FeedbackTarget
    """What it is on: a run, a firing or a chain."""
    value: dict[str, Any] = Field(default_factory=dict[str, Any])
    """The feedback type's fields."""


@dataclass(frozen=True)
class _Spec:
    name: str
    description: str
    action: str
    arguments: type[_Arguments]
    tier: Tier = "write"
    reversibility: Reversibility = "irreversible"
    effects: frozenset[Effect] = frozenset()
    toolset: Toolset = "automations"
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
    _Spec(
        "reflexr.publish_event",
        "Publish an event to the workspace's log, for its rules to act on. An event is a fact: "
        "it stays in the log.",
        "reflexr:publish",
        _Publish,
        route=None,
    ),
    _read(
        "reflexr.read_events",
        "Read the workspace's log, oldest first: a window of envelopes after and before "
        "sequence numbers, optionally of some types.",
        "reflexr:read_events",
        _Events,
        route=None,
    ),
    _read(
        "reflexr.list_rules",
        "List the rules registered in code, which every workspace evaluates.",
        "reflexr:read_rules",
        _Nothing,
        route=RULES,
    ),
    _read(
        "reflexr.rule_status",
        "Show each of the workspace's rules: in code or stored, on or off, how far behind the "
        "log it is, and its dead letters.",
        "reflexr:read_rules",
        _Nothing,
        route=RULES,
    ),
    _read(
        "reflexr.get_rule",
        "Read one of the workspace's rules, with a stored rule's version and provenance.",
        "reflexr:read_rules",
        _Rule,
        route=RULE,
    ),
    _read(
        "reflexr.rule_history",
        "Read a stored rule's versions, oldest first, with who made each change.",
        "reflexr:read_rules",
        _Rule,
        route=RULE,
    ),
    _read(
        "reflexr.schedule_status",
        "Show each schedule that ticks in the workspace: when it last ticked and ticks next.",
        "reflexr:read_schedules",
        _Nothing,
        route=RULES,
    ),
    _Spec(
        "reflexr.replay_rule",
        "Evaluate a rule again from a sequence number: rebuild its state quietly, or refire its "
        "actions, which run again.",
        "reflexr:replay_rule",
        _Replay,
        route=RULE,
    ),
    _Spec(
        "reflexr.install_rule",
        "Store a rule in the workspace, which acts on events logged after it.",
        "reflexr:install_rule",
        _Install,
        reversibility="compensable",
        route=RULE,
    ),
    _Spec(
        "reflexr.update_rule",
        "Replace a stored rule with a new version; a new condition or scope resets it.",
        "reflexr:update_rule",
        _Update,
        reversibility="compensable",
        route=RULE,
    ),
    _Spec(
        "reflexr.archive_rule",
        "Archive a stored rule, so it stops, and cancel its unfinished runs.",
        "reflexr:archive_rule",
        _Archive,
        route=RULE,
    ),
    _read(
        "reflexr.list_runs",
        "List the workspace's runs, newest first, optionally of one rule, scope or status.",
        "reflexr:read_runs",
        _Runs,
        route=RUNS,
    ),
    _read(
        "reflexr.get_run",
        "Read a run as it stands: its status, attempts, error, output and checkpoint.",
        "reflexr:read_runs",
        _Run,
        exposure="both",
        route=RUNS,
        resource="reflexr://{tenant}/{workspace}/runs/{run_id}",
    ),
    _Spec(
        "reflexr.retry_run",
        "Make a run runnable now, with a fresh retry budget if it had finished; its action runs "
        "again.",
        "reflexr:retry_run",
        _Run,
        route=RUNS,
    ),
    _Spec(
        "reflexr.skip_run",
        "Give up on a waiting or dead-lettered run, unblocking its scope.",
        "reflexr:skip_run",
        _Settle,
        route=RUNS,
    ),
    _Spec(
        "reflexr.cancel_run",
        "Cancel a run that hasn't finished, stopping it if it is running.",
        "reflexr:cancel_run",
        _Settle,
        route=RUNS,
    ),
    _read(
        "reflexr.list_dead_letters",
        "List the events the workspace's rules couldn't evaluate, optionally of one rule.",
        "reflexr:read_dead_letters",
        _DeadLetters,
        route=RULES,
    ),
    _Spec(
        "reflexr.give_feedback",
        "Give feedback of a type the application registers on a run, a firing or a chain.",
        "reflexr:give_feedback",
        _Feedback,
        reversibility="compensable",
        toolset="feedback",
        route=RUNS,
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


class ReflexrCommands:
    """reflexr's static catalog: lattice-core's ``Commands``, with no I/O and no scope."""

    def __init__(self) -> None:
        self._commands = tuple(_command(spec) for spec in _SPECS)

    def commands(self) -> Iterable[Command]:
        """Return reflexr's commands, in the order they are declared."""
        return self._commands


CATALOG: Final = ReflexrCommands()
"""reflexr's catalog, unbound: what an application binds at its composition root."""


READ_LIMIT: Final = 50
"""How many envelopes ``reflexr.read_events`` reads when it is given neither ``limit`` nor
``last``, as reflexr's MCP server does."""

type ActorFor = Callable[[CallContext], UserActor | ExternalAgentActor]
"""How a call's context becomes the actor its workspace is opened as."""


def actor_for(context: CallContext) -> UserActor | ExternalAgentActor:
    """Return the actor a call acts as: the outside client it came through, or else its caller.

    - A call through an outside client (``via``) is that client's
      :class:`~reflexr.core.ExternalAgentActor`, by its connection's id and name, for the person
      the caller is or acts for (lattice RFC-0014).
    - A person's own call is their :class:`~reflexr.core.UserActor`.
    - An agent's run is an outside agent's, ``agent:<agent>``, and a code session's is
      ``session:<id>``, each for the person it acts for, if it acts for one. Neither is a rule's
      own :class:`~reflexr.core.AgentActor`.

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


class CommandRejected(Rejection):
    """A command the workspace refused: its rejection, as reflexr's surfaces send it."""

    def __init__(self, rejection: dict[str, JsonValue]) -> None:
        super().__init__(str(rejection.get("message", "rejected")))
        self._rejection = rejection

    def payload(self) -> dict[str, JsonValue]:
        """Return the rejection as the workspace gave it."""
        return dict(self._rejection)


_BY_NAME: Final = MappingProxyType({spec.name: spec for spec in _SPECS})


class ReflexrProvider(ReflexrCommands):
    """reflexr's catalog bound to its workspaces: lattice-core's ``Provider`` and ``Commands``.

    Each call opens the call's workspace as its actor, so the workspace checks it again, and
    carries a command out once, as every surface does.

    Args:
        workspaces: The application's workspaces.
        actor: How a call's context becomes the actor its workspace is opened as;
            :func:`actor_for` if omitted.
    """

    def __init__(self, workspaces: Workspaces, *, actor: ActorFor = actor_for) -> None:
        super().__init__()
        self.kind: ProviderKind = "command"
        self._workspaces = workspaces
        self._actor = actor
        self._offered = tuple(command.capability for command in self._commands)

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return every command's capability, the same in every workspace.

        Where stored rules are off, installing, updating and archiving one are offered still,
        and refused as they are carried out, as reflexr's surfaces refuse them.
        """
        return self._offered

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Run a command in the call's workspace, as the call's actor, and answer JSON text.

        Raises:
            ValueError: If the capability isn't one of reflexr's commands.
            pydantic.ValidationError: If the arguments aren't the command's.
            reflexr.core.Rejection: If the workspace refuses the actor or the command.
        """
        spec = _BY_NAME.get(capability.name)
        if spec is None:
            raise ValueError(f"{capability.name} isn't one of reflexr's commands")
        given = spec.arguments.model_validate(arguments)
        scope, actor = context.scope, self._actor(context)
        if spec.name == "reflexr.list_rules":
            rules = await self._workspaces.rules_for(scope.tenant_id, actor=actor)
            return ToolResult(output=_listed(rules))
        workspace = await self._workspaces.open(scope.tenant_id, scope.workspace_id, actor=actor)
        return ToolResult(output=await self._run(workspace, spec.name, given))

    async def _run(self, workspace: Workspace, name: str, given: _Arguments) -> str:
        match given:
            case _Publish():
                event = load_event(given.event)
                frame = Publish(event=event, id=given.id, correlation_id=given.correlation_id)
                return await self._execute(workspace, frame)
            case _Events():
                limit = READ_LIMIT if given.limit is None and given.last is None else given.limit
                found = await workspace.read(
                    after_seq=given.after_seq,
                    before_seq=given.before_seq,
                    types=given.types,
                    limit=limit,
                    last=given.last,
                )
                return _listed(found)
            case _Replay():
                frame = ReplayRule(rule=given.rule, from_seq=given.from_seq, mode=given.mode)
                return await self._execute(workspace, frame)
            case _Update():
                frame = UpdateRule(
                    rule=given.rule,
                    expected_version=given.expected_version,
                    provenance=given.provenance or {},
                )
                return await self._execute(workspace, frame)
            case _Install():
                frame = InstallRule(rule=given.rule, provenance=given.provenance or {})
                return await self._execute(workspace, frame)
            case _Archive():
                frame = ArchiveRule(
                    rule=given.rule, expected_version=given.expected_version, reason=given.reason
                )
                return await self._execute(workspace, frame)
            case _Rule() if name == "reflexr.get_rule":
                return (await workspace.get_rule(given.rule)).model_dump_json()
            case _Rule():
                return _listed(await workspace.rule_history(given.rule))
            case _Runs():
                key = None if given.scope_key is None else key_of(given.scope_key)
                found = await workspace.runs(
                    rule=given.rule, scope_key=key, status=given.status, limit=given.limit
                )
                return _listed(found)
            case _Settle() if name == "reflexr.skip_run":
                frame = SkipRun(run_id=given.run_id, reason=given.reason)
                return await self._execute(workspace, frame)
            case _Settle():
                frame = CancelRun(run_id=given.run_id, reason=given.reason)
                return await self._execute(workspace, frame)
            case _Run() if name == "reflexr.retry_run":
                return await self._execute(workspace, RetryRun(run_id=given.run_id))
            case _Run():
                return (await workspace.run(given.run_id)).model_dump_json()
            case _DeadLetters():
                return _listed(await workspace.dead_letters(rule=given.rule))
            case _Feedback():
                frame = GiveFeedback(
                    feedback_type=given.feedback_type, target=given.target, value=given.value
                )
                return await self._execute(workspace, frame)
            case _ if name == "reflexr.rule_status":
                return _listed(await workspace.rule_statuses())
            case _:  # reflexr.schedule_status
                return _listed(await workspace.schedule_statuses())

    async def _execute(self, workspace: Workspace, frame: Frame) -> str:
        """Carry a command out once, under an id of its own, as every surface does.

        Raises:
            CommandRejected: If the workspace refuses it.
        """
        result = await self._workspaces.execute(workspace, frame, command_id=new_id("cmd"))
        if result.rejection is not None:
            raise CommandRejected(result.rejection)
        assert result.outcome is not None, "a result has an outcome or a rejection"
        return result.outcome.model_dump_json()


def _listed(found: Sequence[BaseModel]) -> str:
    return json.dumps([each.model_dump(mode="json") for each in found], sort_keys=True)


def provider(workspaces: Workspaces, *, actor: ActorFor = actor_for) -> ReflexrProvider:
    """Bind reflexr's catalog to the application's workspaces, at its composition root."""
    return ReflexrProvider(workspaces, actor=actor)
