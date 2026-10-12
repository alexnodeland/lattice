"""The bridged event types: artifactr's events as reflexr sees them, in the `artifactr` namespace.

Each is declared under [`ArtifactrEvent`][relayr.events.ArtifactrEvent], whose
`event_namespace="artifactr"` makes every type `artifactr:<name>`, such as
`artifactr:message_posted` (ADR-0006). The envelope's actor in reflexr is relayr's source; who
acted in artifactr is each event's `author`, so rules can filter on it. artifactr's agent runs
are *turns* here, so that "run" means one thing inside reflexr: `run_ended` is bridged as
`artifactr:turn_ended`, and a run's id is a `turn_id`.
"""

from typing import Literal

from pydantic import JsonValue

from artifactr.core import (
    Actor,
    ArtifactId,
    FeedbackTarget,
    MessageId,
    MessageKind,
    Patch,
    ProposalId,
    ProposedChange,
    RunId,
    RunUsage,
    ThreadId,
)
from reflexr import Event


class ArtifactrEvent(Event, abstract=True, event_namespace="artifactr"):
    """The base of the bridged types: what every one says about where it came from."""

    author: Actor
    """Who acted in artifactr: the envelope's actor there."""

    thread_id: ThreadId | None = None
    """The thread it happened in, if any: a chain that begins with it carries the thread."""

    turn_id: RunId | None = None
    """The agent turn that did it, if one did: artifactr's run id."""


class MessagePosted(ArtifactrEvent, name="message_posted"):
    """A message, or a notice, was posted in a thread."""

    message_id: MessageId
    content: str
    kind: MessageKind = "message"


class ArtifactCreated(ArtifactrEvent, name="artifact_created"):
    """An artifact was created at version 1."""

    artifact_id: ArtifactId
    kind: str
    version: int
    data: dict[str, JsonValue]
    proposal_id: ProposalId | None = None
    """The accepted proposal that created it, if one did."""


class ArtifactChanged(ArtifactrEvent, name="artifact_changed"):
    """An artifact was changed by a patch."""

    artifact_id: ArtifactId
    kind: str
    version: int
    summary: str
    patch: Patch
    proposal_id: ProposalId | None = None
    """The accepted proposal that changed it, if one did."""


class ArtifactArchived(ArtifactrEvent, name="artifact_archived"):
    """An artifact was archived."""

    artifact_id: ArtifactId
    kind: str
    version: int
    proposal_id: ProposalId | None = None
    """The accepted proposal that archived it, if one did."""


class ProposalCreated(ArtifactrEvent, name="proposal_created"):
    """A change was proposed."""

    proposal_id: ProposalId
    proposed_by: Actor
    """Who proposed it: its author, named as on `artifactr:proposal_resolved`."""

    change: ProposedChange
    rationale: str | None = None


class ProposalResolved(ArtifactrEvent, name="proposal_resolved"):
    """A proposal was accepted or rejected. Its author is who resolved it."""

    proposal_id: ProposalId
    proposed_by: Actor
    decision: Literal["accept", "reject"]
    artifact_id: ArtifactId
    changes: Patch | None = None
    """The changes made to the proposal as it was accepted, if any."""

    reason: str | None = None
    version: int | None = None
    """The artifact's version the acceptance made."""


class TurnEnded(ArtifactrEvent, name="turn_ended"):
    """An agent turn ended: artifactr's `run_ended`."""

    status: Literal["completed", "stopped", "failed"]
    usage: RunUsage | None = None
    error: str | None = None
    reason: str | None = None


class FeedbackGiven(ArtifactrEvent, name="feedback_given"):
    """A person or an evaluator gave feedback in artifactr. Its author is who gave it."""

    feedback_type: str
    target: FeedbackTarget
    value: dict[str, JsonValue]


BRIDGED: tuple[type[ArtifactrEvent], ...] = (
    MessagePosted,
    ArtifactCreated,
    ArtifactChanged,
    ArtifactArchived,
    ProposalCreated,
    ProposalResolved,
    TurnEnded,
    FeedbackGiven,
)
"""Every bridged type: give them to reflexr's `Workspaces(events=...)`, with the application's
own, so the follower may publish them."""
