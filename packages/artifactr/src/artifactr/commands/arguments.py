"""Each of artifactr's commands' arguments: what its JSON Schema says, and what a provider reads.

The catalog's input schemas are these models' (lattice RFC-0014). A provider bound to the
application's workspaces validates a call's arguments with the model its command names
(:data:`artifactr.commands.ARGUMENTS`) before it carries the command out, as
:class:`artifactr.capabilities.ArtifactrCatalogProvider` does. Each refuses a field it doesn't
know.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Arguments",
    "ArtifactArguments",
    "CreateArguments",
    "DeferredArguments",
    "EditArguments",
    "EditTextArguments",
    "EventsArguments",
    "FeedbackArguments",
    "FeedbackTarget",
    "FileArguments",
    "FocusArguments",
    "ListArguments",
    "ModeArguments",
    "NewThreadArguments",
    "NoArguments",
    "OnArtifact",
    "OnMessage",
    "OnThread",
    "OnTurn",
    "PageArguments",
    "PostArguments",
    "ProposalArguments",
    "ProposeTextArguments",
    "ReadThreadArguments",
    "RunArguments",
    "ThreadArguments",
]


class Arguments(BaseModel):
    """A command's arguments: frozen, and refusing a field they don't know."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class PageArguments(Arguments):
    """A page of a list ordered by id."""

    after: str | None = None
    """Read after this id, from the last page."""
    limit: int = Field(default=100, ge=1, le=500)
    """How many to read."""


class NoArguments(Arguments):
    """No arguments: the command reads its workspace."""


class ThreadArguments(Arguments):
    """One thread."""

    thread_id: str
    """The thread."""


class ReadThreadArguments(ThreadArguments):
    """A thread, and its events after a sequence number."""

    after_seq: int = Field(default=0, ge=0)
    """Read the thread's events after this sequence number, to read what came since."""


class NewThreadArguments(Arguments):
    """A new thread."""

    title: str | None = None
    """Its title; one is made from its first message if omitted."""


class PostArguments(Arguments):
    """A message to post."""

    text: str = Field(min_length=1)
    """The message."""
    thread_id: str | None = None
    """The thread to post in; a new one is started if omitted."""


class RunArguments(Arguments):
    """One run."""

    run_id: str
    """The run."""


class EventsArguments(Arguments):
    """The workspace's events after a sequence number."""

    after_seq: int = Field(default=0, ge=0)
    """Read the workspace's events after this sequence number."""
    limit: int = Field(default=100, ge=1, le=1000)
    """How many to read."""


class ListArguments(Arguments):
    """The workspace's artifacts, optionally of one kind."""

    kind: str | None = None
    """Only list artifacts of this kind."""


class ArtifactArguments(Arguments):
    """One artifact."""

    artifact_id: str
    """The artifact."""


class CreateArguments(Arguments):
    """A new artifact."""

    kind: str
    """The kind of artifact to create: one the application registers."""
    data: dict[str, Any]
    """Its data, which must match its kind's JSON Schema."""


class EditTextArguments(ArtifactArguments):
    """A passage of an artifact's text field to replace."""

    old: str
    """Text that occurs exactly once in the field now; an empty string writes an empty field."""
    new: str
    """The replacement text."""
    field: str = "text"
    """The text field to edit."""
    summary: str | None = None
    """A short description of the change, shown to others."""


class ProposeTextArguments(EditTextArguments):
    """A passage of an artifact's text field to propose replacing."""

    rationale: str | None = None
    """Why you propose it, shown to the person who reviews it."""


class EditArguments(ArtifactArguments):
    """JSON Patch operations on an artifact's data, at the version they were made against."""

    base_version: int = Field(ge=1)
    """The version you read: the edit is refused if the artifact has changed since."""
    operations: list[dict[str, Any]] = Field(min_length=1)
    """JSON Patch operations on the artifact's data."""
    summary: str | None = None
    """A short description of the change, shown to others."""


class ProposalArguments(Arguments):
    """An answer to a proposal."""

    proposal_id: str
    """The proposal."""
    accept: bool
    """Whether to accept it, applying its change, or reject it."""
    reason: str | None = None
    """Why, shown to whoever proposed it."""


class OnArtifact(Arguments):
    """Feedback on one version of an artifact."""

    kind: Literal["artifact"]
    artifact_id: str
    """The artifact."""
    version: int = Field(ge=1)
    """Its version the feedback is on."""


class OnThread(Arguments):
    """Feedback on a whole thread."""

    kind: Literal["thread"]
    thread_id: str
    """The thread."""


class OnTurn(Arguments):
    """Feedback on an agent's turn: its run."""

    kind: Literal["turn"]
    run_id: str
    """The run."""


class OnMessage(Arguments):
    """Feedback on one message in a thread."""

    kind: Literal["message"]
    message_id: str
    """The message."""
    thread_id: str
    """The thread it was posted in."""
    run_id: str | None = None
    """For an agent's message, the run that posted it."""


type FeedbackTarget = Annotated[
    OnArtifact | OnThread | OnTurn | OnMessage, Field(discriminator="kind")
]
"""What feedback is on, by ``kind``: core's targets, as a call names them."""


class FeedbackArguments(Arguments):
    """Feedback of a type the application registers."""

    feedback_type: str = Field(min_length=1)
    """The feedback type: one the application registers."""
    target: FeedbackTarget
    """What the feedback is on: an artifact's version, a thread, a turn or a message."""
    value: dict[str, Any] = Field(default_factory=dict[str, Any])
    """The feedback type's fields."""


class DeferredArguments(Arguments):
    """An answer to a deferred tool's call."""

    call_id: str
    """The deferred call."""
    approved: bool
    """Whether to let it go ahead."""


class FocusArguments(Arguments):
    """What is open beside a thread."""

    artifact_id: str | None
    """What is open; none if omitted."""


class ModeArguments(ThreadArguments):
    """A thread's mode."""

    mode: Literal["edit", "suggest"]
    """``edit`` changes artifacts directly; ``suggest`` proposes changes for people to accept."""


class FileArguments(ArtifactArguments):
    """A page of a native file's text."""

    page: int = Field(default=1, ge=1)
    """The page to read, of a file read a page at a time."""
