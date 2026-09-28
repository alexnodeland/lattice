"""Change notes: what others did, told to the agent."""

from datetime import UTC, datetime
from itertools import count

from artifactr.core import (
    Actor,
    AgentActor,
    AppEvent,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    ChangeNote,
    CreateArtifact,
    EditArtifact,
    Envelope,
    KnownEvent,
    ProposalCreated,
    ProposalNote,
    ProposalResolved,
    TextEdit,
    TextEdits,
    UserActor,
    change_notes,
    render_notes,
)

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")
AGENT = AgentActor(thread_id="t1", run_id="r2")
PATCH = TextEdits(edits=(TextEdit(old="a", new="b"),))
_seq = count(1)


def env(actor: Actor, event: KnownEvent) -> Envelope:
    return Envelope(
        seq=next(_seq),
        id="e",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        workspace_id="w",
        actor=actor,
        event=event,
    )


def changed(artifact_id: str, version: int, summary: str, **extra: object) -> ArtifactChanged:
    return ArtifactChanged(
        artifact_id=artifact_id,
        kind="note",
        version=version,
        patch=PATCH,
        summary=summary,
        **extra,  # type: ignore[arg-type]
    )


def test_changes_by_others_are_coalesced_per_artifact() -> None:
    notes = change_notes(
        [
            env(ALICE, changed("n1", 2, "moved launch")),
            env(BOB, changed("n1", 3, "fixed typo")),
            env(ALICE, changed("n1", 4, "added risks")),
        ],
        viewer=AGENT,
    )
    assert notes == [
        ChangeNote(
            artifact_id="n1",
            kind="note",
            actors=("Alice", "Bob"),
            from_version=1,
            to_version=4,
            summaries=("moved launch", "fixed typo", "added risks"),
        )
    ]
    assert notes[0].render() == (
        "Alice and Bob changed n1 (note, v1 → v4): moved launch; fixed typo; added risks"
    )


def test_the_viewers_own_changes_are_left_out() -> None:
    earlier_run = AgentActor(thread_id="t1", run_id="r1")
    assert change_notes([env(earlier_run, changed("n1", 2, "x"))], viewer=AGENT) == []


def test_focus_limits_notes_but_creations_in_the_viewers_thread_are_kept() -> None:
    notes = change_notes(
        [
            env(ALICE, changed("n1", 2, "followed")),
            env(ALICE, changed("n2", 2, "not followed")),
            env(
                ALICE,
                ArtifactCreated(artifact_id="n3", kind="note", version=1, data={}, thread_id="t1"),
            ),
            env(
                ALICE,
                ArtifactCreated(artifact_id="n4", kind="note", version=1, data={}, thread_id="t9"),
            ),
        ],
        viewer=AGENT,
        focus={"n1"},
    )
    assert [note.artifact_id for note in notes] == ["n1", "n3"]
    assert notes[1].render() == "Alice created n3 (note, v1)"


def test_creation_then_changes_and_archiving() -> None:
    [note] = change_notes(
        [
            env(BOB, ArtifactCreated(artifact_id="n1", kind="note", version=1, data={})),
            env(BOB, changed("n1", 2, "drafted")),
            env(BOB, ArtifactArchived(artifact_id="n1", kind="note", version=3)),
        ],
        viewer=ALICE,
    )
    assert note.render() == "Bob created n1 (note, v3): drafted; archived"


def test_decisions_on_the_viewers_proposals() -> None:
    accepted = ProposalResolved(
        proposal_id="p1",
        decision="accept",
        proposed_by=AGENT,
        artifact_id="n1",
        version=5,
        changes=PATCH,
    )
    rejected = ProposalResolved(
        proposal_id="p2",
        decision="reject",
        proposed_by=AGENT,
        artifact_id="n1",
        reason="too early",
    )
    plain = ProposalResolved(
        proposal_id="p3", decision="accept", proposed_by=AGENT, artifact_id="n2", version=2
    )
    others = ProposalResolved(
        proposal_id="p4", decision="accept", proposed_by=BOB, artifact_id="n1", version=6
    )
    notes = change_notes(
        [
            env(ALICE, changed("n1", 5, "applied", proposal_id="p1")),
            env(ALICE, accepted),
            env(ALICE, rejected),
            env(ALICE, plain),
            env(ALICE, others),
        ],
        viewer=AGENT,
    )
    assert render_notes(notes) == "\n".join(
        [
            "- Alice accepted your proposal p1 for n1, now v5: "
            "with changes: edited text (1 replacement)",
            "- Alice rejected your proposal p2 for n1: too early",
            "- Alice accepted your proposal p3 for n2, now v2",
        ]
    )


def test_proposals_by_others_on_followed_artifacts() -> None:
    edit = EditArtifact(artifact_id="n1", base_version=1, patch=PATCH)
    create = CreateArtifact(artifact_id="n7", kind="note", data={})
    notes = change_notes(
        [
            env(BOB, ProposalCreated(proposal_id="p1", change=edit, rationale="clearer")),
            env(BOB, ProposalCreated(proposal_id="p2", change=create)),
            env(BOB, AppEvent(name="ignored")),
        ],
        viewer=ALICE,
        focus={"n1"},
    )
    assert notes == [
        ProposalNote(
            proposal_id="p1", artifact_id="n1", actor="Bob", action="proposed", detail="clearer"
        )
    ]
    assert notes[0].render() == "Bob proposed a change to n1 (p1): clearer"
    assert (
        ProposalNote(proposal_id="p2", artifact_id="n7", actor="Bob", action="proposed").render()
        == "Bob proposed a change to n7 (p2)"
    )


def test_three_or_more_actors_are_listed_naturally() -> None:
    carol = UserActor(id="carol")
    [note] = change_notes(
        [
            env(ALICE, changed("n1", 2, "a")),
            env(BOB, changed("n1", 3, "b")),
            env(carol, changed("n1", 4, "c")),
        ],
        viewer=AGENT,
    )
    assert note.render().startswith("Alice, Bob and carol changed n1")
    assert ChangeNote(
        artifact_id="n1", kind="note", actors=("Bob",), from_version=1, to_version=2
    ).render() == ("Bob changed n1 (note, v1 → v2)")
