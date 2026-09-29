"""The attributes of artifactr's spans for commands and their outcomes."""

from typing import assert_never

from opentelemetry.util.types import AttributeValue

from artifactr.core import (
    Actor,
    AgentActor,
    AnswerDeferred,
    Applied,
    ArchiveArtifact,
    Command,
    CreateArtifact,
    CreateThread,
    EditArtifact,
    GiveFeedback,
    MessageTarget,
    Outcome,
    PostMessage,
    ProposeChange,
    Proposed,
    Recorded,
    Resolved,
    RespondToProposal,
    RunId,
    SetFocus,
    SetThreadMode,
    TenantId,
    TextEdits,
    ThreadId,
    ThreadTarget,
    TurnTarget,
    WorkspaceId,
)
from artifactr.telemetry.attributes import (
    ARTIFACT_ID,
    ARTIFACT_VERSION,
    COMMAND_TYPE,
    FEEDBACK_TARGET,
    FEEDBACK_TYPE,
    OUTCOME,
    PATCH_KIND,
    PATCH_SIZE,
    PROPOSAL_ID,
    attribution,
)


def command_attributes(
    command: Command, *, tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor
) -> dict[str, AttributeValue]:
    """Return the attributes of a command's span: its type, what it is about, and who sent it.

    They carry ids, kinds and sizes, never content.
    """
    details: dict[str, AttributeValue] = {COMMAND_TYPE: command.type}
    thread_id: ThreadId | None = None
    run_id: RunId | None = None
    match command:
        case CreateArtifact() | EditArtifact() | ArchiveArtifact():
            details |= _change(command)
            thread_id = command.thread_id
        case ProposeChange():
            details |= _change(command.change) | {PROPOSAL_ID: command.proposal_id}
            thread_id = command.change.thread_id
        case RespondToProposal():
            details[PROPOSAL_ID] = command.proposal_id
        case CreateThread() | PostMessage() | SetFocus() | SetThreadMode():
            thread_id = command.thread_id
        case AnswerDeferred():
            run_id = command.run_id
        case GiveFeedback():
            details |= {FEEDBACK_TYPE: command.feedback_type, FEEDBACK_TARGET: command.target.kind}
            match command.target:
                case ThreadTarget(thread_id=thread_id):
                    pass
                case TurnTarget(run_id=run_id):
                    pass
                case MessageTarget(thread_id=thread_id, run_id=run_id):
                    pass
                case _:
                    details |= {
                        ARTIFACT_ID: command.target.artifact_id,
                        ARTIFACT_VERSION: command.target.version,
                    }
        case _:
            assert_never(command)
    if isinstance(actor, AgentActor):
        thread_id = thread_id or actor.thread_id
        run_id = run_id or actor.run_id
    context = attribution(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        run_id=run_id,
        actor=actor,
    )
    return context | details


def _change(change: CreateArtifact | EditArtifact | ArchiveArtifact) -> dict[str, AttributeValue]:
    details: dict[str, AttributeValue] = {ARTIFACT_ID: change.artifact_id}
    if isinstance(change, EditArtifact):
        patch = change.patch
        size = len(patch.edits) if isinstance(patch, TextEdits) else len(patch.ops)
        details |= {PATCH_KIND: patch.kind, PATCH_SIZE: size}
    return details


def outcome_attributes(outcome: Outcome) -> dict[str, AttributeValue]:
    """Return the attributes that record what a command did."""
    details: dict[str, AttributeValue] = {OUTCOME: outcome.type}
    match outcome:
        case Applied():
            details |= {ARTIFACT_ID: outcome.artifact_id, ARTIFACT_VERSION: outcome.version}
        case Proposed():
            details[PROPOSAL_ID] = outcome.proposal_id
        case Resolved():
            details[PROPOSAL_ID] = outcome.proposal_id
            if outcome.version is not None:
                details[ARTIFACT_VERSION] = outcome.version
        case Recorded():
            pass
        case _:
            assert_never(outcome)
    return details
