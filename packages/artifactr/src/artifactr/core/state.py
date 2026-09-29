"""The state core reads, the changes it returns, and the outcomes it reports.

Core is sans-IO (ADR-0001). A host asks :func:`artifactr.core.needs` what to load for a
command, loads it into a :class:`State`, calls :func:`artifactr.core.commit`, and persists the
:class:`CommitResult`: the entities to save and the events to append, in one transaction.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.core.actors import Actor
from artifactr.core.artifacts import Artifact, Versioned
from artifactr.core.commands import ProposedChange, ThreadMode
from artifactr.core.events import DeferredRequest, KnownEvent
from artifactr.core.ids import ArtifactId, ProposalId, RunId, ThreadId, TraceId
from artifactr.core.patches import Patch

# ─── entities ─────────────────────────────────────────────────────────────────


class Thread(BaseModel):
    """A chat, with its mode and the artifacts it is focused on."""

    model_config = ConfigDict(frozen=True)

    id: ThreadId
    title: str = ""
    mode: ThreadMode = "edit"
    focus: tuple[ArtifactId, ...] = ()


class DeferredAnswer(BaseModel):
    """The answer to one deferred request of a paused run."""

    model_config = ConfigDict(frozen=True)

    answer: JsonValue = None
    approved: bool | None = None


RunStatus = Literal["running", "paused", "completed", "stopped", "failed"]


class Run(BaseModel):
    """An agent run, which may pause for deferred requests and resume."""

    model_config = ConfigDict(frozen=True)

    id: RunId
    thread_id: ThreadId
    status: RunStatus = "running"
    pending: tuple[DeferredRequest, ...] = ()
    answers: dict[str, DeferredAnswer] = {}
    trace_ids: tuple[TraceId, ...] = ()
    """The OpenTelemetry trace of each traced attempt, oldest first: a run that pauses and
    resumes runs once per attempt, each in its own trace."""

    @property
    def all_answered(self) -> bool:
        """Whether every pending request of a paused run has been answered."""
        return self.status == "paused" and all(
            request.tool_call_id in self.answers for request in self.pending
        )


class Proposal(BaseModel):
    """A change proposed by one participant for another to accept or reject."""

    model_config = ConfigDict(frozen=True)

    id: ProposalId
    change: ProposedChange
    proposed_by: Actor
    rationale: str | None = None
    status: Literal["pending", "accepted", "rejected"] = "pending"
    thread_id: ThreadId | None = None

    @property
    def artifact_id(self) -> ArtifactId:
        """The artifact the proposal creates, changes or archives."""
        return self.change.artifact_id


class Revision(BaseModel):
    """One immutable version of an artifact (ADR-0004)."""

    model_config = ConfigDict(frozen=True)

    artifact_id: ArtifactId
    version: int
    kind: str
    data: dict[str, JsonValue]
    patch: Patch | None = None
    actor: Actor
    proposal_id: ProposalId | None = None
    archived: bool = False


# ─── outcomes ─────────────────────────────────────────────────────────────────


class _Outcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int | None = None
    """The sequence number of the last event the command appended, set by the workspace."""


class Applied(_Outcome):
    """The change was applied: the artifact is now at ``version``."""

    type: Literal["applied"] = "applied"
    artifact_id: ArtifactId
    version: int


class Proposed(_Outcome):
    """The change was recorded as a proposal instead of being applied."""

    type: Literal["proposed"] = "proposed"
    proposal_id: ProposalId


class Resolved(_Outcome):
    """A proposal was accepted (the artifact is now at ``version``) or rejected."""

    type: Literal["resolved"] = "resolved"
    proposal_id: ProposalId
    decision: Literal["accept", "reject"]
    version: int | None = None


class Recorded(_Outcome):
    """The command was recorded; it changed no artifact."""

    type: Literal["recorded"] = "recorded"


Outcome = Annotated[Applied | Proposed | Resolved | Recorded, Field(discriminator="type")]
"""What a command did, discriminated by ``type``."""


# ─── state in, changes out ────────────────────────────────────────────────────

_EMPTY: Mapping[Any, Any] = MappingProxyType({})


@dataclass(frozen=True)
class State:
    """The slice of a workspace that core needs to decide one command.

    Each mapping holds what the host loaded, keyed by id. A key whose value is ``None`` was
    looked up and does not exist; a missing key was not loaded (see :func:`needs`).
    """

    artifacts: Mapping[ArtifactId, Versioned[Artifact] | None] = field(default=_EMPTY)
    proposals: Mapping[ProposalId, Proposal | None] = field(default=_EMPTY)
    threads: Mapping[ThreadId, Thread | None] = field(default=_EMPTY)
    runs: Mapping[RunId, Run | None] = field(default=_EMPTY)


@dataclass(frozen=True)
class Needs:
    """Ids a host must load into :class:`State` before core can decide a command."""

    artifacts: frozenset[ArtifactId] = frozenset()
    proposals: frozenset[ProposalId] = frozenset()
    threads: frozenset[ThreadId] = frozenset()
    runs: frozenset[RunId] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.artifacts or self.proposals or self.threads or self.runs)


@dataclass(frozen=True)
class CommitResult:
    """Everything a host persists after a command, in one transaction.

    ``artifacts``, ``proposals``, ``threads`` and ``runs`` are entities to insert or replace;
    ``revisions`` are appended; ``events`` are appended to the log in order.
    """

    outcome: Applied | Proposed | Resolved | Recorded
    events: tuple[KnownEvent, ...] = ()
    artifacts: tuple[Versioned[Artifact], ...] = ()
    revisions: tuple[Revision, ...] = ()
    proposals: tuple[Proposal, ...] = ()
    threads: tuple[Thread, ...] = ()
    runs: tuple[Run, ...] = ()
