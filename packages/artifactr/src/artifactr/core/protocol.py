"""The thread protocol: its frames, handshake and resume rule.

A client says ``hello`` with the last ``seq`` it has seen, or asks to start at the head of the
log; :func:`resume` decides where replay starts. Resume is by sequence number, never by
timestamp (ADR-0005). The frame models here are the protocol's source of truth;
``schemas/artifactr.v1.json`` is generated from them.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.core.actors import Actor
from artifactr.core.commands import Command
from artifactr.core.errors import UnsupportedProtocol, ValidationFailed
from artifactr.core.events import Envelope
from artifactr.core.ids import ArtifactId, RunId, ThreadId, WorkspaceId
from artifactr.core.live import LiveFrame
from artifactr.core.state import Applied, Proposed, Recorded, Resolved
from artifactr.core.tagged import tag_required

PROTOCOL: Final = "artifactr.v1"
"""The protocol version this library speaks."""


class Hello(BaseModel):
    """The first frame a client sends on a connection."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["hello"] = "hello"
    protocol: str
    resume_after_seq: int = Field(default=0, ge=0)
    """The last ``seq`` the client has: everything after it is replayed."""

    from_head: bool = False
    """Start at the head of the log instead, replaying nothing. ``resume_after_seq`` must then
    be 0; a client that reconnects resumes from ``welcome.head_seq`` with it."""

    threads: tuple[ThreadId, ...] | None = None
    """Thread-scoped events to receive; ``None`` means every thread."""

    events: bool = True
    """Whether to receive the log's events, and runs' live frames, at all. A connection that is
    only for presence, such as a canvas's, asks for none: it is welcomed, told replay is
    complete, and sent only what it asks for (ADR-0093)."""


class ResumePlan(BaseModel):
    """Where a connection's replay starts."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    replay_after: int
    """Replay every event with a ``seq`` greater than this."""

    reset: bool = False
    """Whether the client must discard what it has and rebuild from the replay."""


def resume(hello: Hello, *, head_seq: int, first_retained_seq: int = 1) -> ResumePlan:
    """Decide where replay starts for a connecting client.

    Args:
        hello: The client's hello frame.
        head_seq: The workspace log's latest ``seq`` (0 if it is empty).
        first_retained_seq: The oldest ``seq`` still stored.

    Raises:
        UnsupportedProtocol: If the client speaks another protocol version.
        ValidationFailed: If the client asks to start at the head and to resume.
    """
    if hello.protocol != PROTOCOL:
        raise UnsupportedProtocol(
            f"this server speaks {PROTOCOL}; the client asked for {hello.protocol}"
        )
    if hello.from_head:
        if hello.resume_after_seq:
            raise ValidationFailed("from_head replays nothing, so resume_after_seq must be 0", [])
        return ResumePlan(replay_after=head_seq)
    oldest_resumable = first_retained_seq - 1
    if hello.resume_after_seq > head_seq or hello.resume_after_seq < oldest_resumable:
        # The client has seen events this log does not have, or ones it no longer keeps.
        return ResumePlan(replay_after=oldest_resumable, reset=True)
    return ResumePlan(replay_after=hello.resume_after_seq)


# ─── frames ───────────────────────────────────────────────────────────────────


class StopRun(BaseModel):
    """Cancel a run. Handled by the transport, not by core's rules."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)

    type: Literal["stop_run"] = "stop_run"
    run_id: RunId


class WatchRun(BaseModel):
    """Receive a run's live frames on this connection. WebSocket only."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)

    type: Literal["watch_run"] = "watch_run"
    run_id: RunId


class WatchArtifact(BaseModel):
    """Receive the presence of the others with an artifact open, and send one's own.

    WebSocket only, as ``watch_run`` is; answered ``watching`` (lattice RFC-0006, ADR-0093).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)

    type: Literal["watch_artifact"] = "watch_artifact"
    artifact_id: ArtifactId


class UnwatchArtifact(BaseModel):
    """Stop watching an artifact: the others are told this connection left it."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)

    type: Literal["unwatch_artifact"] = "unwatch_artifact"
    artifact_id: ArtifactId


FrameCommand = Annotated[
    Command | StopRun | WatchRun | WatchArtifact | UnwatchArtifact, Field(discriminator="type")
]
"""Anything a client can ask for in a command frame."""


class CommandFrame(BaseModel):
    """A client's command, with an id that correlates it with its result.

    ``command_id`` is also an idempotency key: the server deduplicates repeated ids.
    """

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["command"] = "command"
    command_id: str = Field(min_length=1)
    command: FrameCommand


MAX_PRESENCE: Final = 64 * 1024
"""The most characters of JSON a presence frame may be; a longer one is dropped, once read."""


class Pointer(BaseModel):
    """Where a person's pointer is on a canvas, in the scene's own coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)

    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    tool: Literal["pointer", "laser"] = "pointer"
    button: Literal["up", "down"] = "up"


class Presence(BaseModel):
    """Where a person is on an artifact they watch, and what they are changing right now.

    Never stored. ``editing`` holds whole elements, relative to ``base_version``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)

    type: Literal["presence"] = "presence"
    artifact_id: ArtifactId
    seq: int = Field(ge=0)
    """Per connection, increasing. The others are told each peer's frames in the order it sent
    them, and a watcher keeps only the latest it was told."""
    base_version: int = Field(ge=1)
    pointer: Pointer | None = None
    selection: tuple[str, ...] = Field((), max_length=500)
    editing: tuple[dict[str, JsonValue], ...] = Field((), max_length=100)


ClientFrame = Annotated[Hello | CommandFrame | Presence, Field(discriminator="type")]
"""Any frame a client sends."""


class ActiveRun(BaseModel):
    """A run in progress, as listed in ``welcome``."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    run_id: RunId
    thread_id: ThreadId


class Welcome(BaseModel):
    """The server's answer to ``hello``."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["welcome"] = "welcome"
    protocol: str = PROTOCOL
    workspace_id: WorkspaceId
    head_seq: int
    reset: bool = False
    active_runs: tuple[ActiveRun, ...] = ()


class EventFrame(Envelope):
    """A durable event, delivered in its envelope."""

    type: Literal["event"] = "event"


class ReplayComplete(BaseModel):
    """Every event up to ``up_to_seq`` has been replayed; what follows is live."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["replay_complete"] = "replay_complete"
    up_to_seq: int


class Watching(BaseModel):
    """A watch accepted: what the watcher may do on the artifact, ``view`` or ``edit``."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["watching"] = "watching"
    artifact_id: ArtifactId
    rights: Literal["view", "edit"]
    peer: str
    """This connection, as the others know it: a ``peer_left`` naming it says its watch ended."""


ResultOutcome = Annotated[
    Applied | Proposed | Resolved | Recorded | Watching, Field(discriminator="type")
]
"""What a command frame did: a command's outcome, or a watch accepted."""


class PeerPresence(BaseModel):
    """Another connection's presence on an artifact this one watches.

    ``peer`` is opaque, one per connection; ``actor`` is whom the server says it is, never what
    the client said.
    """

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["peer_presence"] = "peer_presence"
    artifact_id: ArtifactId
    peer: str
    actor: Actor
    seq: int
    base_version: int
    pointer: Pointer | None = None
    selection: tuple[str, ...] = ()
    editing: tuple[dict[str, JsonValue], ...] = ()


class PeerLeft(BaseModel):
    """A peer closed an artifact, left, lost its access, or fell silent."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["peer_left"] = "peer_left"
    artifact_id: ArtifactId
    peer: str


class CommandResult(BaseModel):
    """The result of one command frame."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["command_result"] = "command_result"
    command_id: str
    ok: bool
    outcome: ResultOutcome | None = None
    rejection: dict[str, JsonValue] | None = None


class ErrorFrame(BaseModel):
    """A frame the server could not understand, or a failure it could not attribute."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["error"] = "error"
    message: str


ServerFrame = Annotated[
    Welcome
    | EventFrame
    | ReplayComplete
    | LiveFrame
    | CommandResult
    | ErrorFrame
    | PeerPresence
    | PeerLeft,
    Field(discriminator="type"),
]
"""Any frame the server sends."""
