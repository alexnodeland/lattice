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
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from lattice_core.capabilities import Capability, Effect, Gate, JsonObject, Reversibility, Tier
from lattice_core.commands import Command, Exposure, NotExposed, Surface, Toolset
from reflexr.core import FeedbackTarget, Rule, RunStatus

__all__ = ["CATALOG", "LISTED", "VERSION", "ReflexrCommands"]

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
