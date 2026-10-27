"""Live frames: a run's token-level output, delivered best-effort (ADR-0007).

Live frames are never stored and have no ``seq``. Durable events supersede them: when the
agent's ``message_posted`` arrives it is the authoritative text, and ``artifact_changed``
replaces any ``draft`` of that artifact.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.core.events import RunUsage, StepUsage
from artifactr.core.ids import ArtifactId, RunId
from artifactr.core.tagged import tag_required


class _LiveEvent(BaseModel):
    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)


class PartStarted(_LiveEvent):
    """The model started a response part: text, thinking, or a tool call."""

    type: Literal["part_started"] = "part_started"
    part: int
    part_kind: Literal["text", "thinking", "tool_call"]
    tool_name: str | None = None


class TextDelta(_LiveEvent):
    """More text for a text part."""

    type: Literal["text_delta"] = "text_delta"
    part: int
    delta: str
    offset: int | None = None
    """Where ``delta`` starts in the part, in UTF-16 code units from the part's start, as
    JavaScript indexes a string, when the sender counts: a client that is sent a delta again,
    as a run's frames are replayed on reconnect, writes it where it belongs rather than
    appending it twice; one past the end of what it has is appended. ``None`` from a sender
    that doesn't count, as earlier versions didn't."""


class ThinkingDelta(_LiveEvent):
    """More text for a thinking part."""

    type: Literal["thinking_delta"] = "thinking_delta"
    part: int
    delta: str
    offset: int | None = None
    """Where ``delta`` starts in the part, as for a text delta."""


class ToolArgsDelta(_LiveEvent):
    """More of a tool call's JSON arguments."""

    type: Literal["tool_args_delta"] = "tool_args_delta"
    part: int
    delta: str


class PartEnded(_LiveEvent):
    """A response part is complete."""

    type: Literal["part_ended"] = "part_ended"
    part: int


class Draft(_LiveEvent):
    """A full snapshot of an artifact being generated, not yet committed."""

    type: Literal["draft"] = "draft"
    kind: str
    data: dict[str, JsonValue]
    artifact_id: ArtifactId | None = None


class AppLive(_LiveEvent):
    """An application's own live event."""

    type: Literal["app_live"] = "app_live"
    name: str
    data: JsonValue = None


class UsageUpdate(_LiveEvent):
    """What a model request used, as the provider counted it, and what the run has so far.

    Sent as each request's response ends (ADR-0096). ``total`` is the run's whole count so far,
    not an increment, so a client that is sent the frame again, as a run's frames are replayed
    on reconnect, counts nothing twice: it takes the total with the most requests.
    """

    type: Literal["usage"] = "usage"
    step: int
    """The request's index among the run segment's requests, from 0: a resumed run counts
    from 0 again, and its ``total`` with it."""
    usage: StepUsage
    total: RunUsage
    """The run's usage so far, this request's included; its ``steps`` are left out."""
    exact: bool = True
    """Whether the counts are the provider's own rather than an estimate; always true from this
    version, which sends no estimate."""


LiveEvent = Annotated[
    PartStarted
    | TextDelta
    | ThinkingDelta
    | ToolArgsDelta
    | PartEnded
    | Draft
    | AppLive
    | UsageUpdate,
    Field(discriminator="type"),
]
"""Any live event, discriminated by ``type``."""


class LiveFrame(BaseModel):
    """A live event of one run, as sent on the wire."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    type: Literal["live"] = "live"
    run_id: RunId
    event: LiveEvent
