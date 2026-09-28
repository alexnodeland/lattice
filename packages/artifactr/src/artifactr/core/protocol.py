"""The thread protocol's handshake and resume rule.

A client says ``hello`` with the last ``seq`` it has seen; :func:`resume` decides where replay
starts. Resume is by sequence number, never by timestamp (ADR-0005).
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from artifactr.core.errors import UnsupportedProtocol
from artifactr.core.ids import ThreadId

PROTOCOL: Final = "artifactr.v1"
"""The protocol version this library speaks."""


class Hello(BaseModel):
    """The first frame a client sends on a connection."""

    model_config = ConfigDict(frozen=True)

    type: Literal["hello"] = "hello"
    protocol: str
    resume_after_seq: int = Field(default=0, ge=0)
    threads: tuple[ThreadId, ...] | None = None
    """Thread-scoped events to receive; ``None`` means every thread."""


class ResumePlan(BaseModel):
    """Where a connection's replay starts."""

    model_config = ConfigDict(frozen=True)

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
    """
    if hello.protocol != PROTOCOL:
        raise UnsupportedProtocol(
            f"this server speaks {PROTOCOL}; the client asked for {hello.protocol}"
        )
    oldest_resumable = first_retained_seq - 1
    if hello.resume_after_seq > head_seq or hello.resume_after_seq < oldest_resumable:
        # The client has seen events this log does not have, or ones it no longer keeps.
        return ResumePlan(replay_after=oldest_resumable, reset=True)
    return ResumePlan(replay_after=hello.resume_after_seq)
