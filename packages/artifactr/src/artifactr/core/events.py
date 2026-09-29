"""Events: facts appended to a workspace's log.

Core events form a closed union (ADR-0005): code that handles them can ``match`` exhaustively,
and pyright checks it. Applications record their own facts through the one open family,
:class:`AppEvent`. Events from a newer protocol version that this version does not know
validate as :class:`UnknownEvent` instead of failing, so old clients keep working.

Each stored event travels in an :class:`Envelope` that adds its sequence number, id,
timestamp, scope and actor. The envelope's shape is also the wire shape.
"""

from collections.abc import Collection
from datetime import datetime
from typing import Annotated, Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Discriminator, Field, JsonValue, Tag

from artifactr.core.actors import Actor
from artifactr.core.commands import ProposedChange, ThreadMode
from artifactr.core.ids import (
    ArtifactId,
    MessageId,
    ProposalId,
    RunId,
    ThreadId,
    TraceId,
    WorkspaceId,
)
from artifactr.core.patches import Patch


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True)


# ─── threads and messages ─────────────────────────────────────────────────────


class ThreadCreated(_Event):
    """A thread was created."""

    type: Literal["thread_created"] = "thread_created"
    thread_id: ThreadId
    title: str


class ThreadModeChanged(_Event):
    """A thread switched between ``edit`` and ``suggest`` mode."""

    type: Literal["thread_mode_changed"] = "thread_mode_changed"
    thread_id: ThreadId
    mode: ThreadMode


class FocusChanged(_Event):
    """The set of artifacts a thread is focused on changed."""

    type: Literal["focus_changed"] = "focus_changed"
    thread_id: ThreadId
    artifact_ids: tuple[ArtifactId, ...]


class MessagePosted(_Event):
    """A message was posted in a thread. Its author is the envelope's actor."""

    type: Literal["message_posted"] = "message_posted"
    thread_id: ThreadId
    message_id: MessageId
    content: str
    run_id: RunId | None = None


# ─── artifacts and proposals ──────────────────────────────────────────────────


class ArtifactCreated(_Event):
    """An artifact was created at version 1."""

    type: Literal["artifact_created"] = "artifact_created"
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    artifact_id: ArtifactId
    kind: str
    version: int
    data: dict[str, JsonValue]
    proposal_id: ProposalId | None = None


class ArtifactChanged(_Event):
    """An artifact was changed by a patch."""

    type: Literal["artifact_changed"] = "artifact_changed"
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    artifact_id: ArtifactId
    kind: str
    version: int
    patch: Patch
    summary: str
    proposal_id: ProposalId | None = None


class ArtifactArchived(_Event):
    """An artifact was archived."""

    type: Literal["artifact_archived"] = "artifact_archived"
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    artifact_id: ArtifactId
    kind: str
    version: int
    proposal_id: ProposalId | None = None


class ProposalCreated(_Event):
    """A change was proposed."""

    type: Literal["proposal_created"] = "proposal_created"
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    proposal_id: ProposalId
    change: ProposedChange
    rationale: str | None = None


class ProposalResolved(_Event):
    """A proposal was accepted or rejected."""

    type: Literal["proposal_resolved"] = "proposal_resolved"
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    proposal_id: ProposalId
    decision: Literal["accept", "reject"]
    proposed_by: Actor
    artifact_id: ArtifactId
    changes: Patch | None = None
    reason: str | None = None
    version: int | None = None


# ─── agent runs ───────────────────────────────────────────────────────────────


class DeferredRequest(BaseModel):
    """A tool call a paused run is waiting on: a question to answer or a call to approve."""

    model_config = ConfigDict(frozen=True)

    tool_call_id: str
    tool_name: str
    kind: Literal["question", "approval"]
    args: dict[str, JsonValue] = {}


class RunUsage(BaseModel):
    """Token and request counts for a run."""

    model_config = ConfigDict(frozen=True)

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class RunStarted(_Event):
    """An agent run started, or resumed after a pause."""

    type: Literal["run_started"] = "run_started"
    run_id: RunId
    thread_id: ThreadId
    trigger: Literal["message", "resume", "api"] = "message"
    trace_id: TraceId | None = None
    """The OpenTelemetry trace this attempt runs in, when it is traced."""


class ToolCalled(_Event):
    """The agent called a tool."""

    type: Literal["tool_called"] = "tool_called"
    run_id: RunId
    thread_id: ThreadId
    tool_call_id: str
    tool_name: str
    args_summary: str = ""


class ToolReturned(_Event):
    """A tool call finished."""

    type: Literal["tool_returned"] = "tool_returned"
    run_id: RunId
    thread_id: ThreadId
    tool_call_id: str
    status: Literal["ok", "error", "retry"]
    summary: str = ""
    tool_name: str = ""
    """The tool's name, as in its ``tool_called``; empty in events from earlier versions."""


class RunPaused(_Event):
    """A run paused until the listed requests are answered."""

    type: Literal["run_paused"] = "run_paused"
    run_id: RunId
    thread_id: ThreadId
    requests: tuple[DeferredRequest, ...] = Field(min_length=1)
    usage: RunUsage | None = None
    """What the run used up to the pause."""


class DeferredAnswered(_Event):
    """A paused run's request was answered."""

    type: Literal["deferred_answered"] = "deferred_answered"
    run_id: RunId
    thread_id: ThreadId
    tool_call_id: str
    answer: JsonValue = None
    approved: bool | None = None


class RunEnded(_Event):
    """An agent run ended."""

    type: Literal["run_ended"] = "run_ended"
    run_id: RunId
    thread_id: ThreadId
    status: Literal["completed", "stopped", "failed"]
    usage: RunUsage | None = None
    error: str | None = None


# ─── extension ────────────────────────────────────────────────────────────────


class AppEvent(_Event):
    """An application-defined fact. ``name`` identifies it; ``data`` is free-form JSON."""

    type: Literal["app_event"] = "app_event"
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    name: str
    data: JsonValue = None


class UnknownEvent(BaseModel):
    """An event type this version does not know, kept as-is so it round-trips."""

    model_config = ConfigDict(frozen=True, extra="allow")

    type: str


KnownEvent = (
    ThreadCreated
    | ThreadModeChanged
    | FocusChanged
    | MessagePosted
    | ArtifactCreated
    | ArtifactChanged
    | ArtifactArchived
    | ProposalCreated
    | ProposalResolved
    | RunStarted
    | ToolCalled
    | ToolReturned
    | RunPaused
    | DeferredAnswered
    | RunEnded
    | AppEvent
)
"""Every event type this version defines."""

RunEvent = RunStarted | ToolCalled | ToolReturned | RunPaused | RunEnded
"""Facts about agent runs, recorded by the agent layer rather than commanded."""

_KNOWN_TAGS = frozenset(
    event_type.model_fields["type"].default for event_type in get_args(KnownEvent)
)


def _event_tag(value: object) -> str:
    if isinstance(value, dict):
        tag = cast("dict[str, object]", value).get("type")
    else:
        tag = getattr(value, "type", None)
    return tag if isinstance(tag, str) and tag in _KNOWN_TAGS else "unknown"


def scope_of(event: KnownEvent) -> tuple[ThreadId | None, RunId | None]:
    """Return the thread and run an event belongs to, for its envelope."""
    return getattr(event, "thread_id", None), getattr(event, "run_id", None)


Event = Annotated[
    Annotated[ThreadCreated, Tag("thread_created")]
    | Annotated[ThreadModeChanged, Tag("thread_mode_changed")]
    | Annotated[FocusChanged, Tag("focus_changed")]
    | Annotated[MessagePosted, Tag("message_posted")]
    | Annotated[ArtifactCreated, Tag("artifact_created")]
    | Annotated[ArtifactChanged, Tag("artifact_changed")]
    | Annotated[ArtifactArchived, Tag("artifact_archived")]
    | Annotated[ProposalCreated, Tag("proposal_created")]
    | Annotated[ProposalResolved, Tag("proposal_resolved")]
    | Annotated[RunStarted, Tag("run_started")]
    | Annotated[ToolCalled, Tag("tool_called")]
    | Annotated[ToolReturned, Tag("tool_returned")]
    | Annotated[RunPaused, Tag("run_paused")]
    | Annotated[DeferredAnswered, Tag("deferred_answered")]
    | Annotated[RunEnded, Tag("run_ended")]
    | Annotated[AppEvent, Tag("app_event")]
    | Annotated[UnknownEvent, Tag("unknown")],
    Discriminator(_event_tag),
]
"""Any event, discriminated by ``type``; unknown types validate as :class:`UnknownEvent`."""


class Envelope(BaseModel):
    """A stored event with its position and attribution. Its shape is also the wire shape."""

    model_config = ConfigDict(frozen=True)

    seq: int = Field(ge=1)
    """The event's position in its workspace's log, gap-free from 1."""

    id: str
    ts: datetime
    workspace_id: WorkspaceId
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    actor: Actor
    event: Event


_WORKSPACE_SCOPED = (
    ArtifactCreated,
    ArtifactChanged,
    ArtifactArchived,
    ProposalCreated,
    ProposalResolved,
)


def delivered_to(envelope: Envelope, threads: Collection[ThreadId] | None) -> bool:
    """Return whether a subscriber following ``threads`` receives ``envelope``.

    Workspace-scoped events (artifacts and proposals) reach every subscriber, whichever thread
    they originated in. Thread-scoped events reach subscribers that follow their thread.
    ``None`` follows every thread.
    """
    if threads is None or envelope.thread_id is None:
        return True
    return isinstance(envelope.event, _WORKSPACE_SCOPED) or envelope.thread_id in threads
