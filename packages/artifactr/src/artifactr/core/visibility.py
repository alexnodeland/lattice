"""What an actor may not see in a workspace, and how what it reads looks without it.

A thread or artifact is visible to the workspace unless the application restricts it (lattice
RFC-0001). The application's ``hidden`` hook answers with the exceptions for one actor, and
every read leaves them out: a hidden item is missing, an envelope about one is dropped, and an
artifact event committed from a hidden thread keeps its artifact's history whole but loses the
thread and run it came from.
"""

from collections.abc import Set as AbstractSet
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from artifactr.core.actors import Actor, AgentActor
from artifactr.core.artifacts import Artifact, Versioned
from artifactr.core.events import (
    WORKSPACE_SCOPED,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    Envelope,
    Event,
    FeedbackGiven,
    FocusChanged,
    ProposalCreated,
    ProposalResolved,
    ToolCalled,
    ToolReturned,
)
from artifactr.core.feedback import ArtifactTarget
from artifactr.core.ids import ArtifactId, ThreadId
from artifactr.core.state import Proposal, Revision, Thread


class Hides(Protocol):
    """The threads and artifacts an actor may not see in one workspace.

    :class:`Visibility` is one; so is any object with these two sets, such as an access
    library's own answer.
    """

    @property
    def threads(self) -> AbstractSet[ThreadId]:
        """The threads hidden from the actor."""
        ...

    @property
    def artifacts(self) -> AbstractSet[ArtifactId]:
        """The artifacts hidden from the actor."""
        ...


class Visibility(BaseModel):
    """The threads and artifacts an actor may not see in one workspace: nothing by default."""

    model_config = ConfigDict(frozen=True)

    threads: frozenset[ThreadId] = frozenset()
    artifacts: frozenset[ArtifactId] = frozenset()


def hides_nothing(hidden: Hides) -> bool:
    """Whether nothing is hidden, so every read is as stored."""
    return not hidden.threads and not hidden.artifacts


def artifact_of(envelope: Envelope) -> ArtifactId | None:
    """The artifact an envelope's event is about, if it is about one."""
    match envelope.event:
        case ArtifactCreated() | ArtifactChanged() | ArtifactArchived() | ProposalResolved():
            return envelope.event.artifact_id
        case ProposalCreated(change=change):
            return change.artifact_id
        case FeedbackGiven(target=ArtifactTarget(artifact_id=artifact_id)):
            return artifact_id
        case ToolCalled() | ToolReturned():
            return envelope.event.artifact_id
        case _:
            return None


def seen(envelope: Envelope, hidden: Hides) -> Envelope | None:
    """An envelope as an actor who may not see ``hidden`` reads it, or None if they don't.

    An envelope about a hidden artifact, or in a hidden thread, is dropped, but for an artifact
    or proposal event from a hidden thread: it is kept, without the thread, run and trace it
    came from, so a visible artifact's history stays whole. Nothing kept names a hidden thread
    or artifact: a hidden thread's agent is named without its thread, and a focus without
    hidden artifacts.
    """
    if hides_nothing(hidden):
        return envelope
    if artifact_of(envelope) in hidden.artifacts:
        return None
    from_hidden = envelope.thread_id in hidden.threads
    if from_hidden and envelope.event.type not in WORKSPACE_SCOPED:
        return None
    update: dict[str, object] = {
        "actor": seen_actor(envelope.actor, hidden),
        "event": _seen_event(envelope.event, hidden),
    }
    if from_hidden:
        update |= {"thread_id": None, "run_id": None, "traceparent": None}
    return envelope.model_copy(update=update)


def _seen_event(event: Event, hidden: Hides) -> Event:
    """An event kept for an actor, without the hidden threads and artifacts it names."""
    update: dict[str, object] = {}
    if getattr(event, "thread_id", None) in hidden.threads:
        update |= {"thread_id": None, "run_id": None}
    match event:
        case FocusChanged(artifact_ids=focus):
            update["artifact_ids"] = tuple(a for a in focus if a not in hidden.artifacts)
        case ProposalCreated(change=change) if change.thread_id in hidden.threads:
            update["change"] = change.model_copy(update={"thread_id": None})
        case ProposalResolved(proposed_by=proposer):
            update["proposed_by"] = seen_actor(proposer, hidden)
        case _:
            pass
    return event.model_copy(update=update) if update else event


def seen_actor(actor: Actor, hidden: Hides) -> Actor:
    """An actor as one who may not see ``hidden`` reads it.

    A hidden thread's agent names no thread or run.
    """
    if isinstance(actor, AgentActor) and actor.thread_id in hidden.threads:
        return actor.model_copy(update={"thread_id": "", "run_id": None})
    return actor


def seen_artifact[A: Artifact](artifact: Versioned[A], hidden: Hides) -> Versioned[A]:
    """A visible artifact as the actor reads it: a hidden thread's agent names no thread."""
    return artifact.model_copy(update={"updated_by": seen_actor(artifact.updated_by, hidden)})


def seen_revision(revision: Revision, hidden: Hides) -> Revision:
    """A visible artifact's revision as the actor reads it.

    One made by a hidden thread's agent names neither its thread nor the trace it ran in.
    """
    actor = seen_actor(revision.actor, hidden)
    if actor == revision.actor:
        return revision
    return revision.model_copy(update={"actor": actor, "trace_id": None})


def seen_thread(thread: Thread, hidden: Hides) -> Thread:
    """A visible thread as the actor reads it: its focus without hidden artifacts."""
    if hidden.artifacts.isdisjoint(thread.focus):
        return thread
    return thread.model_copy(
        update={"focus": tuple(a for a in thread.focus if a not in hidden.artifacts)}
    )


def seen_proposal(proposal: Proposal, hidden: Hides) -> Proposal | None:
    """A proposal as the actor reads it, or None if its artifact is hidden.

    A proposal from a hidden thread is kept, without the thread or its agent's.
    """
    if proposal.artifact_id in hidden.artifacts:
        return None
    thread, change = proposal.thread_id, proposal.change
    return proposal.model_copy(
        update={
            "proposed_by": seen_actor(proposal.proposed_by, hidden),
            "thread_id": None if thread in hidden.threads else thread,
            "change": (
                change.model_copy(update={"thread_id": None})
                if change.thread_id in hidden.threads
                else change
            ),
        }
    )
