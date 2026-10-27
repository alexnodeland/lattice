"""Commands: intents to change a workspace.

Commands are the only way anything changes (ADR-0002). Every surface, from agent tools to
REST, WebSocket and MCP, turns its input into one of these and submits it through
``Workspace.commit``. Commands carry the identifiers of anything they create, so core stays
deterministic.
"""

from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, model_validator

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
from artifactr.core.tagged import tag_required

ThreadMode = Literal["edit", "suggest"]
"""How agents change artifacts in a thread: directly, or always through proposals."""

MessageKind = Literal["message", "notice"]
"""What a message is for: the thread's agent acts on a ``message``, while a ``notice`` informs
people and starts or steers no turn (ADR-0051)."""


def _not_empty(value: str) -> str:
    if not value:
        raise ValueError("an id is never empty")
    return value


_NOT_EMPTY: Final = AfterValidator(_not_empty)
"""What an id a command gives a new item must be: not empty, so the item's route reaches it
(ADR-0063). It is checked, not documented, so the id keeps its schema."""


class _Command(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=tag_required)


class CreateArtifact(_Command):
    """Create an artifact.

    If the artifact type's write policy (or the thread's mode) requires an agent to propose,
    the command is recorded as a proposal with ``proposal_id`` instead.
    """

    type: Literal["create_artifact"] = "create_artifact"
    artifact_id: Annotated[ArtifactId, _NOT_EMPTY] = Field(default_factory=new_artifact_id)
    kind: str
    data: dict[str, JsonValue]
    thread_id: ThreadId | None = None
    proposal_id: Annotated[ProposalId, _NOT_EMPTY] = Field(default_factory=new_proposal_id)


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
    proposal_id: Annotated[ProposalId, _NOT_EMPTY] = Field(default_factory=new_proposal_id)


class ArchiveArtifact(_Command):
    """Archive an artifact. Archived artifacts can be read but not changed."""

    type: Literal["archive_artifact"] = "archive_artifact"
    artifact_id: ArtifactId
    base_version: int = Field(ge=1)
    thread_id: ThreadId | None = None
    proposal_id: Annotated[ProposalId, _NOT_EMPTY] = Field(default_factory=new_proposal_id)


ProposedChange = Annotated[
    CreateArtifact | EditArtifact | ArchiveArtifact, Field(discriminator="type")
]
"""A change that a proposal would make when accepted."""


class ProposeChange(_Command):
    """Propose a change for someone else to accept, whatever the write policy."""

    type: Literal["propose_change"] = "propose_change"
    proposal_id: Annotated[ProposalId, _NOT_EMPTY] = Field(default_factory=new_proposal_id)
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
    thread_id: Annotated[ThreadId, _NOT_EMPTY] = Field(default_factory=new_thread_id)
    title: str = ""


class PostMessage(_Command):
    """Post a message, or a notice, in a thread, attributed to the actor who commits it."""

    type: Literal["post_message"] = "post_message"
    thread_id: ThreadId
    message_id: Annotated[MessageId, _NOT_EMPTY] = Field(default_factory=new_message_id)
    content: str = Field(min_length=1)
    kind: MessageKind = "message"
    model: str | None = Field(default=None, min_length=1)
    """The model to answer with, by the name the host's ``model_for`` knows (ADR-0097), or the
    thread's default when ``None``. It applies when this message starts a new turn: one that
    joins a running turn, through its watcher, is answered by the turn's model. A notice
    starts no turn, so it names none."""

    @model_validator(mode="after")
    def _no_model_on_notice(self) -> Self:
        if self.kind == "notice" and self.model is not None:
            raise ValueError("a notice starts no turn, so it names no model")
        return self


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
