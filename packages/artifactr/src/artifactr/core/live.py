"""Live frames: a run's token-level output, delivered best-effort (ADR-0007).

Live frames are never stored and have no ``seq``. Durable events supersede them: when the
agent's ``message_posted`` arrives it is the authoritative text, and ``artifact_changed``
replaces any ``draft`` of that artifact.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.core.ids import ArtifactId, RunId


class _LiveEvent(BaseModel):
    model_config = ConfigDict(frozen=True)


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


class ThinkingDelta(_LiveEvent):
    """More text for a thinking part."""

    type: Literal["thinking_delta"] = "thinking_delta"
    part: int
    delta: str


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


LiveEvent = Annotated[
    PartStarted | TextDelta | ThinkingDelta | ToolArgsDelta | PartEnded | Draft | AppLive,
    Field(discriminator="type"),
]
"""Any live event, discriminated by ``type``."""


class LiveFrame(BaseModel):
    """A live event of one run, as sent on the wire."""

    model_config = ConfigDict(frozen=True)

    type: Literal["live"] = "live"
    run_id: RunId
    event: LiveEvent
