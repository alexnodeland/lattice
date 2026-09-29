"""Commands: intents to change a workspace.

Commands are the only way anything changes (ADR-0002). Every surface, from agent tools to
REST, WebSocket and MCP, turns its input into one of these and submits it through
``Workspace.commit``. Commands carry the identifiers of anything they create, so core stays
deterministic.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.core.feedback import FeedbackTarget
from artifactr.core.ids import (
    ArtifactId,
    MessageId,
    ProposalId,
    RunId,
    ThreadId,
    new_artifact_id,
    new_message_id,
    new_proposal_id,
    new_thread_id,
)
from artifactr.core.patches import Patch

ThreadMode = Literal["edit", "suggest"]
"""How agents change artifacts in a thread: directly, or always through proposals."""


class _Command(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CreateArtifact(_Command):
    """Create an artifact.

    If the artifact type's write policy (or the thread's mode) requires an agent to propose,
    the command is recorded as a proposal with ``proposal_id`` instead.
    """

    type: Literal["create_artifact"] = "create_artifact"
    artifact_id: ArtifactId = Field(default_factory=new_artifact_id)
    kind: str
    data: dict[str, JsonValue]
    thread_id: ThreadId | None = None
    proposal_id: ProposalId = Field(default_factory=new_proposal_id)


class EditArtifact(_Command):
    """Apply a patch to an artifact, based on a specific version.

    If the artifact type's write policy (or the thread's mode) requires an agent to propose,
    the command is recorded as a proposal with ``proposal_id`` instead.
    """

    type: Literal["edit_artifact"] = "edit_artifact"
    artifact_id: ArtifactId
    base_version: int = Field(ge=1)
    patch: Patch
    summary: str | None = None
    thread_id: ThreadId | None = None
    proposal_id: ProposalId = Field(default_factory=new_proposal_id)


class ArchiveArtifact(_Command):
    """Archive an artifact. Archived artifacts can be read but not changed."""

    type: Literal["archive_artifact"] = "archive_artifact"
    artifact_id: ArtifactId
    base_version: int = Field(ge=1)
    thread_id: ThreadId | None = None
    proposal_id: ProposalId = Field(default_factory=new_proposal_id)


ProposedChange = Annotated[
    CreateArtifact | EditArtifact | ArchiveArtifact, Field(discriminator="type")
]
"""A change that a proposal would make when accepted."""


class ProposeChange(_Command):
    """Propose a change for someone else to accept, whatever the write policy."""

    type: Literal["propose_change"] = "propose_change"
    proposal_id: ProposalId = Field(default_factory=new_proposal_id)
    change: ProposedChange
    rationale: str | None = None


class RespondToProposal(_Command):
    """Accept or reject a pending proposal.

    ``changes`` is an optional patch applied on top of the proposed result when accepting, so a
    person can accept a proposal with their own edits.
    """

    type: Literal["respond_to_proposal"] = "respond_to_proposal"
    proposal_id: ProposalId
    decision: Literal["accept", "reject"]
    changes: Patch | None = None
    reason: str | None = None


class CreateThread(_Command):
    """Create a thread."""

    type: Literal["create_thread"] = "create_thread"
    thread_id: ThreadId = Field(default_factory=new_thread_id)
    title: str = ""


class PostMessage(_Command):
    """Post a message in a thread, attributed to the actor who commits it."""

    type: Literal["post_message"] = "post_message"
    thread_id: ThreadId
    message_id: MessageId = Field(default_factory=new_message_id)
    content: str = Field(min_length=1)


class SetFocus(_Command):
    """Set the artifacts a thread is focused on."""

    type: Literal["set_focus"] = "set_focus"
    thread_id: ThreadId
    artifact_ids: tuple[ArtifactId, ...]


class SetThreadMode(_Command):
    """Switch a thread between ``edit`` and ``suggest`` mode."""

    type: Literal["set_thread_mode"] = "set_thread_mode"
    thread_id: ThreadId
    mode: ThreadMode


class AnswerDeferred(_Command):
    """Answer a paused run's question, or approve or deny one of its tool calls."""

    type: Literal["answer_deferred"] = "answer_deferred"
    run_id: RunId
    tool_call_id: str
    answer: JsonValue = None
    approved: bool | None = None


class GiveFeedback(_Command):
    """Give feedback of a registered type on an artifact version, a thread, a turn or a message.

    ``value`` holds the feedback type's fields; core validates it against the type, checks the
    type can be given on the target, and checks the target exists.
    """

    type: Literal["give_feedback"] = "give_feedback"
    feedback_type: str
    target: FeedbackTarget
    value: dict[str, JsonValue] = {}


Command = Annotated[
    CreateArtifact
    | EditArtifact
    | ArchiveArtifact
    | ProposeChange
    | RespondToProposal
    | CreateThread
    | PostMessage
    | SetFocus
    | SetThreadMode
    | AnswerDeferred
    | GiveFeedback,
    Field(discriminator="type"),
]
"""Any command, discriminated by ``type``."""
