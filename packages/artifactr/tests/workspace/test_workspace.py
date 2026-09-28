"""Workspace behaviour, independent of the storage implementation."""

import asyncio
from datetime import timedelta

import pytest

from artifactr.core import (
    AgentActor,
    AppEvent,
    Applied,
    Artifact,
    CreateArtifact,
    EditArtifact,
    MarkdownArtifact,
    NotFound,
    ProposeChange,
    Proposed,
    Recorded,
    RespondToProposal,
    RunEnded,
    RunStarted,
    SetFocus,
    VersionConflict,
)
from artifactr.workspace import ThreadBusy, Workspace, Workspaces
from tests.artifact_types import Checklist, Counter, Item, Note
from tests.workspace.conftest import ALICE

AGENT = AgentActor(thread_id="thr_1", run_id="run_1")


async def test_create_then_read_typed(ws: Workspace) -> None:
    created = await ws.create(Note(title="Plan", text="Ship Friday"), artifact_id="n1")
    assert created == Applied(artifact_id="n1", version=1, seq=1)
    note = await ws.get(Note, "n1")
    assert (note.version, note.data.title, note.updated_by) == (1, "Plan", ALICE)
    assert type(note.data) is Note
    assert (await ws.artifact("n1")).model_dump(mode="json") == {
        "id": "n1",
        "version": 1,
        "data": {"text": "Ship Friday", "title": "Plan"},
        "updated_by": {"kind": "user", "id": "alice", "name": "Alice"},
        "archived": False,
        "kind": "note",
    }


async def test_reading_as_the_wrong_type_is_not_found(ws: Workspace) -> None:
    await ws.create(Note(), artifact_id="n1")
    with pytest.raises(NotFound) as missing:
        await ws.get(Checklist, "n1")
    assert (missing.value.entity, missing.value.id) == ("checklist", "n1")
    with pytest.raises(NotFound):
        await ws.artifact("nope")


async def test_listing_filters_by_type_including_abstract_bases(ws: Workspace) -> None:
    await ws.create(Note(), artifact_id="n1")
    await ws.create(Checklist(), artifact_id="c1")
    await ws.create(Counter(), artifact_id="k1")
    assert [a.id for a in await ws.artifacts()] == ["n1", "c1", "k1"]
    assert [a.id for a in await ws.artifacts(MarkdownArtifact)] == ["n1"]
    assert [a.data.count for a in await ws.artifacts(Counter)] == [0]


async def test_edits_advance_versions_and_revisions(ws: Workspace) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    note = await ws.get(Note, "n1")
    outcome = await ws.commit(note.edit_text("Friday", "Monday"))
    assert outcome == Applied(artifact_id="n1", version=2, seq=2)
    assert (await ws.get(Note, "n1")).data.text == "Ship Monday"
    assert [r.version for r in await ws.revisions("n1")] == [1, 2]
    with pytest.raises(VersionConflict):
        await ws.commit(note.edit_text("Friday", "Sunday"))
    assert await ws.head_seq() == 2


async def test_a_rejected_command_changes_nothing(ws: Workspace) -> None:
    await ws.create(Note(text="a"), artifact_id="n1")
    note = await ws.get(Note, "n1")
    with pytest.raises(Exception, match="not found"):
        await ws.commit(note.edit_text("zzz", "b"))
    assert await ws.head_seq() == 1
    assert (await ws.get(Note, "n1")).version == 1


async def test_archived_artifacts_are_hidden_unless_asked_for(ws: Workspace) -> None:
    await ws.create(Note(), artifact_id="n1")
    await ws.commit((await ws.get(Note, "n1")).archive())
    assert await ws.artifacts() == []
    assert [a.archived for a in await ws.artifacts(include_archived=True)] == [True]


async def test_tenants_are_isolated(workspaces: Workspaces) -> None:
    mine = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    theirs = await workspaces.open("tenant_b", "ws_1", actor=ALICE)
    await mine.create(Note(), artifact_id="n1")
    assert await theirs.artifacts() == []
    assert await theirs.head_seq() == 0
    with pytest.raises(NotFound):
        await theirs.artifact("n1")


async def test_only_the_applications_types_can_be_created(storage: object) -> None:
    workspaces = Workspaces(storage, types=[Note])  # type: ignore[arg-type]
    ws = await workspaces.open("t", "w", actor=ALICE)
    await ws.create(Note(), artifact_id="n1")
    with pytest.raises(NotFound, match="artifact type checklist"):
        await ws.create(Checklist())
    create = CreateArtifact(artifact_id="c9", kind="checklist", data={})
    with pytest.raises(NotFound):
        await ws.commit(ProposeChange(change=create))


async def test_agents_propose_and_people_resolve(ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    assert agent.actor.kind == "agent"
    assert agent.workspace_id == "ws_1"
    await ws.create(Checklist(items={"t1": Item(title="Docs")}), artifact_id="c1")
    checklist = await agent.get(Checklist, "c1")

    def check(c: Checklist) -> None:
        c.items["t1"].done = True

    proposed = await agent.commit(checklist.edit(check))
    assert isinstance(proposed, Proposed)
    [pending] = await ws.proposals()
    assert (pending.id, pending.thread_id) == (proposed.proposal_id, thread.id)
    assert isinstance(pending.change, EditArtifact)
    assert pending.change.summary == "checked 'Docs'", "the stored change keeps its summary"
    assert await ws.proposal(pending.id) == pending
    resolved = await ws.commit(RespondToProposal(proposal_id=pending.id, decision="accept"))
    assert (resolved.decision, resolved.version) == ("accept", 2)
    assert (await ws.get(Checklist, "c1")).data.items["t1"].done
    assert await ws.proposals() == []
    assert [p.status for p in await ws.proposals(status=None)] == ["accepted"]
    with pytest.raises(NotFound):
        await ws.proposal("prp_nope")


async def test_threads_and_messages(ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    assert (await ws.thread(thread.id)).title == "Launch"
    assert await ws.threads() == [thread]
    posted = await ws.post_message(thread.id, "Hello")
    assert isinstance(posted, Recorded)
    assert posted.seq == 2
    with pytest.raises(NotFound):
        await ws.thread("thr_nope")


async def test_a_command_without_events_has_no_seq(ws: Workspace) -> None:
    thread = await ws.create_thread()
    assert await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=())) == Recorded()


async def test_runs_and_history_are_recorded_together(ws: Workspace) -> None:
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id))
    assert (await ws.run("run_1")).status == "running"
    ended = RunEnded(run_id="run_1", thread_id=thread.id, status="completed")
    await agent.record(ended, history=b'[{"kind":"request"}]')
    assert (await ws.run("run_1")).status == "completed"
    [chunk] = await ws.history(thread.id)
    assert (chunk.seq, chunk.messages) == (3, b'[{"kind":"request"}]')
    with pytest.raises(NotFound):
        await ws.run("run_nope")


async def test_runs_are_listed_by_thread_and_status(ws: Workspace) -> None:
    one, two = await ws.create_thread(), await ws.create_thread()
    for run_id, thread in (("run_1", one), ("run_2", two), ("run_3", one)):
        agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id=run_id))
        await agent.record(RunStarted(run_id=run_id, thread_id=thread.id))
    agent = ws.as_actor(AgentActor(thread_id=one.id, run_id="run_1"))
    await agent.record(RunEnded(run_id="run_1", thread_id=one.id, status="completed"))
    assert [r.id for r in await ws.runs()] == ["run_1", "run_2", "run_3"]
    assert [r.id for r in await ws.runs(thread_id=one.id)] == ["run_1", "run_3"]
    assert [r.id for r in await ws.runs(status="running")] == ["run_2", "run_3"]
    assert [r.id for r in await ws.runs(thread_id=one.id, status="running")] == ["run_3"]


async def test_history_needs_a_thread(ws: Workspace) -> None:
    await ws.record(AppEvent(name="exported"), history=b"[]")
    assert await ws.head_seq() == 1


async def test_reading_the_log_by_thread(ws: Workspace) -> None:
    one = await ws.create_thread("one")
    two = await ws.create_thread("two")
    await ws.post_message(one.id, "in one")
    await ws.post_message(two.id, "in two")
    await ws.commit(CreateArtifact(artifact_id="n1", kind="note", data={}, thread_id=two.id))
    everything = await ws.read()
    assert [e.seq for e in everything] == [1, 2, 3, 4, 5]
    only_one = await ws.read(threads={one.id})
    assert [e.event.type for e in only_one] == [
        "thread_created",
        "message_posted",
        "artifact_created",
    ]
    assert [e.seq for e in await ws.read(after_seq=3, limit=1)] == [4]


async def test_subscribing_replays_then_follows_live(ws: Workspace) -> None:
    one = await ws.create_thread("one")  # seq 1: replayed
    two = await ws.create_thread("two")  # seq 2: another thread's, filtered out
    received: list[int] = []

    async def follow() -> None:
        async for envelope in ws.subscribe(threads={one.id}):
            received.append(envelope.seq)
            if len(received) == 3:
                return

    follower = asyncio.create_task(follow())
    await asyncio.sleep(0)
    await ws.post_message(two.id, "not followed")  # seq 3: filtered out
    await ws.post_message(one.id, "followed")  # seq 4: live
    await ws.create(Note(), artifact_id="n1")  # seq 5: workspace-scoped, always delivered
    await asyncio.wait_for(follower, timeout=2)
    assert received == [1, 4, 5]


async def test_change_notes_are_from_the_viewers_point_of_view(ws: Workspace) -> None:
    thread = await ws.create_thread()
    await ws.create(Note(text="Friday"), artifact_id="n1", thread_id=thread.id)
    await ws.commit((await ws.get(Note, "n1")).edit_text("Friday", "Monday"))
    agent = ws.as_actor(AgentActor(thread_id=thread.id))
    [note] = await agent.change_notes(after_seq=0, focus={"n1"})
    assert note.render() == "Alice created n1 (note, v2): edited text (1 replacement)"
    assert await ws.change_notes(after_seq=0) == []
    assert len(await ws.change_notes(after_seq=0, viewer=AGENT)) == 1


async def test_a_thread_is_claimed_by_one_run_at_a_time(ws: Workspace) -> None:
    thread = await ws.create_thread()
    async with ws.claim_thread(thread.id, holder="run_1"):
        with pytest.raises(ThreadBusy):
            async with ws.claim_thread(thread.id, holder="run_2"):
                pass
    async with ws.claim_thread(thread.id, holder="run_2"):
        pass


async def test_a_claim_is_renewed_while_held(ws: Workspace) -> None:
    thread = await ws.create_thread()
    # Renewed every ttl/3, so the claim lapses only if a renewal stalls for most of the ttl.
    ttl = timedelta(milliseconds=300)
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl):
        await asyncio.sleep(0.5)  # longer than the ttl: only renewal keeps the claim
        with pytest.raises(ThreadBusy):
            async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
                pass


def test_subclassing_artifact_is_all_it_takes() -> None:
    assert issubclass(Note, Artifact)
