"""Projections: which artifactr envelopes become reflexr events, and as what.

[`bridged`][relayr.events.bridged] maps the default set, RFC-0002's: messages, artifacts,
proposals, ended turns and feedback. Everything else stays in artifactr: thread and focus
changes, run starts and pauses, tool calls and deferred answers. An application adds its own
with [`Projections`][relayr.events.Projections]: a function per `app_event` name, and per
artifact kind, which publishes the application's types, in its own namespace.

An envelope becomes at most one event, so the event's id can be the envelope's.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TypedDict

import artifactr.core as a
from reflexr import Event
from relayr.events.types import (
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    ArtifactrEvent,
    FeedbackGiven,
    MessagePosted,
    ProposalCreated,
    ProposalResolved,
    TurnEnded,
)

type Projection = Callable[[a.Envelope], Event | None]
"""Maps an artifactr envelope to the reflexr event it becomes, or to None to bridge nothing.

An exception, a pydantic `ValidationError` included, dead-letters the envelope.
"""


class _Origin(TypedDict):
    """The fields every bridged event takes from its envelope."""

    author: a.Actor
    thread_id: a.ThreadId | None
    turn_id: a.RunId | None


def bridged(envelope: a.Envelope) -> ArtifactrEvent | None:
    """Return the default set's event for an envelope, or None for an event it leaves out."""
    origin = _Origin(author=envelope.actor, thread_id=envelope.thread_id, turn_id=envelope.run_id)
    match envelope.event:
        case a.MessagePosted() as event:
            return MessagePosted(
                **origin, message_id=event.message_id, content=event.content, kind=event.kind
            )
        case a.ArtifactCreated() as event:
            return ArtifactCreated(
                **origin,
                artifact_id=event.artifact_id,
                kind=event.kind,
                version=event.version,
                data=event.data,
                proposal_id=event.proposal_id,
            )
        case a.ArtifactChanged() as event:
            return ArtifactChanged(
                **origin,
                artifact_id=event.artifact_id,
                kind=event.kind,
                version=event.version,
                summary=event.summary,
                patch=event.patch,
                proposal_id=event.proposal_id,
            )
        case a.ArtifactArchived() as event:
            return ArtifactArchived(
                **origin,
                artifact_id=event.artifact_id,
                kind=event.kind,
                version=event.version,
                proposal_id=event.proposal_id,
            )
        case a.ProposalCreated() as event:
            return ProposalCreated(
                **origin,
                proposal_id=event.proposal_id,
                proposed_by=envelope.actor,
                change=event.change,
                rationale=event.rationale,
            )
        case a.ProposalResolved() as event:
            return ProposalResolved(
                **origin,
                proposal_id=event.proposal_id,
                proposed_by=event.proposed_by,
                decision=event.decision,
                artifact_id=event.artifact_id,
                changes=event.changes,
                reason=event.reason,
                version=event.version,
            )
        case a.RunEnded() as event:
            return TurnEnded(
                **origin,
                status=event.status,
                usage=event.usage,
                error=event.error,
                reason=event.reason,
            )
        case a.FeedbackGiven() as event:
            return FeedbackGiven(
                **origin,
                feedback_type=event.feedback_type,
                target=event.target,
                value=event.value,
            )
        case _:
            return None


class Projections:
    """What the follower publishes for each envelope: the default set, and the application's.

    Args:
        app_events: A projection per `app_event` name. An `app_event` with none stays in
            artifactr.
        artifacts: A projection per artifact kind, for its `artifact_created`,
            `artifact_changed` and `artifact_archived`, in place of the default set's events.
            Proposals on the kind are bridged as the default set's.
    """

    def __init__(
        self,
        *,
        app_events: Mapping[str, Projection] | None = None,
        artifacts: Mapping[str, Projection] | None = None,
    ) -> None:
        self._app_events = MappingProxyType(dict(app_events or {}))
        self._artifacts = MappingProxyType(dict(artifacts or {}))

    def project(self, envelope: a.Envelope) -> Event | None:
        """Return the event an envelope becomes, or None if it stays in artifactr.

        Raises:
            Exception: Whatever a projection raises, a pydantic `ValidationError` included.
        """
        match envelope.event:
            case a.AppEvent(name=name):
                projection = self._app_events.get(name)
            case (
                a.ArtifactCreated(kind=kind)
                | a.ArtifactChanged(kind=kind)
                | a.ArtifactArchived(kind=kind)
            ) if kind in self._artifacts:
                projection = self._artifacts[kind]
            case _:
                projection = bridged
        return None if projection is None else projection(envelope)
