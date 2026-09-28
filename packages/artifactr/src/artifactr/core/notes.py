"""Change notes: what others did, told to the agent (ADR-0008).

:func:`change_notes` turns a slice of the log into short, attributed notes. It keeps only
what the viewer should hear about: changes by *other* participants to the artifacts the
viewer is focused on (or created in the viewer's thread), proposals others made on those
artifacts, and decisions on the viewer's own proposals.
"""

from collections.abc import Collection, Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from artifactr.core.actors import Actor, AgentActor, same_participant
from artifactr.core.events import (
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    Envelope,
    ProposalCreated,
    ProposalResolved,
)
from artifactr.core.ids import ArtifactId, ProposalId
from artifactr.core.patches import describe_patch


class ChangeNote(BaseModel):
    """What other participants did to one artifact, coalesced across events."""

    model_config = ConfigDict(frozen=True)

    type: Literal["change"] = "change"
    artifact_id: ArtifactId
    kind: str
    actors: tuple[str, ...]
    from_version: int | None
    """The version before the changes, or None if the artifact was created."""
    to_version: int
    summaries: tuple[str, ...] = ()

    def render(self) -> str:
        """Return the note as one line of text."""
        who = _join(self.actors)
        if self.from_version is None:
            head = f"{who} created {self.artifact_id} ({self.kind}, v{self.to_version})"
        else:
            span = f"v{self.from_version} → v{self.to_version}"
            head = f"{who} changed {self.artifact_id} ({self.kind}, {span})"
        return f"{head}: {'; '.join(self.summaries)}" if self.summaries else head


class ProposalNote(BaseModel):
    """A proposal made by someone else, or a decision on the viewer's own proposal."""

    model_config = ConfigDict(frozen=True)

    type: Literal["proposal"] = "proposal"
    proposal_id: ProposalId
    artifact_id: ArtifactId
    actor: str
    action: Literal["proposed", "accepted", "rejected"]
    detail: str | None = None
    version: int | None = None

    def render(self) -> str:
        """Return the note as one line of text."""
        if self.action == "proposed":
            text = f"{self.actor} proposed a change to {self.artifact_id} ({self.proposal_id})"
        else:
            text = f"{self.actor} {self.action} your proposal {self.proposal_id}"
            text += f" for {self.artifact_id}"
            if self.version is not None:
                text += f", now v{self.version}"
        return f"{text}: {self.detail}" if self.detail else text


Note = ChangeNote | ProposalNote


def change_notes(
    envelopes: Iterable[Envelope],
    *,
    viewer: Actor,
    focus: Collection[ArtifactId] | None = None,
) -> list[Note]:
    """Return notes about what others did, in the order it happened.

    Args:
        envelopes: A slice of the log, in ``seq`` order.
        viewer: Who the notes are for; their own actions are left out.
        focus: The artifacts the viewer follows. ``None`` means every artifact.

    Returns:
        One :class:`ChangeNote` per artifact others changed, and one :class:`ProposalNote` per
        relevant proposal event.
    """
    envelopes = list(envelopes)
    own_proposals = {
        env.event.proposal_id
        for env in envelopes
        if isinstance(env.event, ProposalResolved)
        and same_participant(env.event.proposed_by, viewer)
    }
    thread_id = viewer.thread_id if isinstance(viewer, AgentActor) else None
    slots: list[ArtifactId | ProposalNote] = []
    changes: dict[ArtifactId, _Accumulator] = {}
    for env in envelopes:
        event = env.event
        if same_participant(env.actor, viewer):
            continue
        match event:
            case ArtifactCreated() | ArtifactChanged() | ArtifactArchived():
                if event.proposal_id in own_proposals:
                    continue  # reported by the proposal's decision
                followed = focus is None or event.artifact_id in focus
                created_here = isinstance(event, ArtifactCreated) and event.thread_id == thread_id
                if not (followed or created_here):
                    continue
                if event.artifact_id not in changes:
                    changes[event.artifact_id] = _Accumulator(event)
                    slots.append(event.artifact_id)
                changes[event.artifact_id].add(event, env.actor.display_name)
            case ProposalCreated():
                artifact_id = event.change.artifact_id
                if focus is None or artifact_id in focus:
                    slots.append(
                        ProposalNote(
                            proposal_id=event.proposal_id,
                            artifact_id=artifact_id,
                            actor=env.actor.display_name,
                            action="proposed",
                            detail=event.rationale,
                        )
                    )
            case ProposalResolved():
                if event.proposal_id in own_proposals:
                    slots.append(_decision_note(event, env.actor.display_name))
            case _:
                pass
    return [changes[slot].note() if isinstance(slot, str) else slot for slot in slots]


def render_notes(notes: Iterable[Note]) -> str:
    """Render notes as a bulleted list, one line each."""
    return "\n".join(f"- {note.render()}" for note in notes)


def _decision_note(event: ProposalResolved, actor: str) -> ProposalNote:
    if event.decision == "reject":
        return ProposalNote(
            proposal_id=event.proposal_id,
            artifact_id=event.artifact_id,
            actor=actor,
            action="rejected",
            detail=event.reason,
        )
    return ProposalNote(
        proposal_id=event.proposal_id,
        artifact_id=event.artifact_id,
        actor=actor,
        action="accepted",
        detail=f"with changes: {describe_patch(event.changes)}" if event.changes else None,
        version=event.version,
    )


class _Accumulator:
    def __init__(self, first: ArtifactCreated | ArtifactChanged | ArtifactArchived) -> None:
        self.artifact_id = first.artifact_id
        self.kind = first.kind
        self.from_version = None if isinstance(first, ArtifactCreated) else first.version - 1
        self.to_version = first.version
        self.actors: dict[str, None] = {}
        self.summaries: list[str] = []

    def add(self, event: ArtifactCreated | ArtifactChanged | ArtifactArchived, actor: str) -> None:
        self.actors[actor] = None
        self.to_version = event.version
        if isinstance(event, ArtifactChanged):
            self.summaries.append(event.summary)
        elif isinstance(event, ArtifactArchived):
            self.summaries.append("archived")

    def note(self) -> ChangeNote:
        return ChangeNote(
            artifact_id=self.artifact_id,
            kind=self.kind,
            actors=tuple(self.actors),
            from_version=self.from_version,
            to_version=self.to_version,
            summaries=tuple(self.summaries),
        )


def _join(names: tuple[str, ...]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"
