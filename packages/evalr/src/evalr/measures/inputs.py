"""The inputs end-to-end measures read, in terms any application's log can be put in.

The libraries' ``[evals]`` extras turn their logs into these: artifactr a thread's messages and an
artifact's revisions, reflexr a causal chain's runs and the operator's actions.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["Activity", "History", "Revision", "Role", "Session", "Transcript", "Turn"]

type Role = Literal["person", "agent", "system"]
"""Who acted: a person, an agent, or the system itself."""


class Activity(BaseModel, frozen=True):
    """Something that happened in a session.

    Attributes:
        at: When.
        role: Who did it.
        kind: What: ``message`` by default, ``proposal`` for a change awaiting a person's
            decision, and ``resolution`` for that decision. Other kinds count as activity.
        ref: Pairs a proposal with its resolution.
    """

    at: datetime
    role: Role
    kind: str = "message"
    ref: str | None = None


class Session(BaseModel):
    """A conversation or a causal chain, as a timeline of activity."""

    id: str
    activities: list[Activity] = Field(description="Everything that happened, oldest first")


class Revision(BaseModel, frozen=True):
    """One version of something an agent and people both write, such as an artifact.

    Attributes:
        at: When it was written.
        role: Who wrote it.
        text: Its whole content, as text.
    """

    at: datetime
    role: Role
    text: str


class History(BaseModel):
    """The revisions of one artifact, oldest first."""

    id: str
    revisions: list[Revision]


class Turn(BaseModel, frozen=True):
    """One turn of a conversation."""

    role: Role
    text: str


class Transcript(BaseModel):
    """What a judge reads to decide whether a task was completed."""

    request: str = Field(description="What the person asked for")
    turns: list[Turn] = Field(description="The conversation, oldest first")
    result: str | None = Field(
        default=None, description="What was produced: the final artifact or report, as text"
    )
