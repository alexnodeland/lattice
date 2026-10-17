"""Workspace behaviour, independent of the storage implementation."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from artifactr.core import (
    Actor,
    AgentActor,
    AppEvent,
    Applied,
    Artifact,
    ArtifactTarget,
    CreateArtifact,
    CreateThread,
    EditArtifact,
    EvaluatorActor,
    ExternalAgentActor,
    FeedbackGiven,
    Forbidden,
    GiveFeedback,
    InvalidState,
    MarkdownArtifact,
    NotFound,
    PostMessage,
    ProposeChange,
    Proposed,
    Recorded,
    RespondToProposal,
    RunEnded,
    RunStarted,
    SetFocus,
    ThreadTarget,
    TurnTarget,
    UserActor,
    ValidationFailed,
    VersionConflict,
)
from artifactr.workspace import (
    Access,
    InMemoryStorage,
    Scope,
    Storage,
    ThreadBusy,
    Workspace,
    Workspaces,
)
from tests.artifact_types import Checklist, Counter, Item, Note
from tests.leases import Partitioned
from tests.workspace.conftest import ALICE, StorageFactory

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
    with pytest.raises(NotFound):
        await ws.revisions("n2")
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


async def test_only_the_applications_types_can_be_created(storage: Storage) -> None:
    workspaces = Workspaces(storage, types=[Note])
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


async def test_no_one_accepts_their_own_proposal_through_an_agent(ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    await ws.create(Note(text="Friday"), artifact_id="n1")
    edit = (await ws.get(Note, "n1")).edit_text("Friday", "Monday")
    mine = await ws.commit(ProposeChange(change=edit))
    run = AgentActor(thread_id=thread.id, run_id="run_1", on_behalf_of=ALICE)
    client = ExternalAgentActor(client_id="claude", on_behalf_of=ALICE)
    for proxy in (run, client, AgentActor(thread_id=thread.id, on_behalf_of=client)):
        accept = RespondToProposal(proposal_id=mine.proposal_id, decision="accept")
        with pytest.raises(Forbidden, match="someone other than its author"):
            await ws.as_actor(proxy).commit(accept)
    via_mcp = await ws.as_actor(client).commit(ProposeChange(change=edit))
    accept = RespondToProposal(proposal_id=via_mcp.proposal_id, decision="accept")
    with pytest.raises(Forbidden, match="someone other than its author"):
        await ws.commit(accept)  # proposed through Alice's own client, accepted in the UI
    theirs = await ws.as_actor(run).commit(ProposeChange(change=edit))
    assert (await ws.proposal(theirs.proposal_id)).proposed_by == run, "stored with its person"
    assert (await ws.read(last=1))[0].actor == run
    accept = RespondToProposal(proposal_id=theirs.proposal_id, decision="accept")
    resolved = await ws.commit(accept)
    assert resolved.decision == "accept", "a person accepts what a run for them proposes"


async def test_threads_and_messages(ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    assert (await ws.thread(thread.id)).title == "Launch"
    assert await ws.threads() == [thread]
    posted = await ws.post_message(thread.id, "Hello")
    assert isinstance(posted, Recorded)
    assert posted.seq == 2
    with pytest.raises(NotFound):
        await ws.thread("thr_nope")


async def test_a_message_id_is_used_once_in_a_workspace(
    workspaces: Workspaces, ws: Workspace
) -> None:
    one = await ws.create_thread("one")
    two = await ws.create_thread("two")
    await ws.post_message(one.id, "Ship Monday", message_id="m1")
    head = await ws.head_seq()
    for thread in (one, two):
        with pytest.raises(InvalidState, match="message m1 already exists"):
            await ws.post_message(thread.id, "Ship Monday", message_id="m1")
    agent = ws.as_actor(AgentActor(thread_id=one.id, run_id="run_1"))
    with pytest.raises(InvalidState):
        await agent.post_message(one.id, "Done.", message_id="m1")
    assert await ws.head_seq() == head, "a refused message appends nothing"
    for tenant_id, workspace_id in (("tenant_a", "ws_2"), ("tenant_b", "ws_1")):
        elsewhere = await workspaces.open(tenant_id, workspace_id, actor=ALICE)
        thread = await elsewhere.create_thread("one")
        posted = await elsewhere.post_message(thread.id, "Ship Monday", message_id="m1")
        assert posted.seq == 2, "message ids are per workspace"


async def test_a_command_without_events_has_no_seq(ws: Workspace) -> None:
    thread = await ws.create_thread()
    assert await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=())) == Recorded()


async def test_runs_and_history_are_recorded_together(ws: Workspace) -> None:
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id, trace_id=trace_id))
    run = await ws.run("run_1")
    assert (run.status, run.trace_ids) == ("running", (trace_id,))
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


async def test_reading_the_log_from_its_end(ws: Workspace) -> None:
    one = await ws.create_thread("one")
    two = await ws.create_thread("two")
    await ws.post_message(one.id, "in one")
    await ws.post_message(two.id, "in two")
    tail = await ws.read(threads={one.id}, last=1)
    assert [e.seq for e in tail] == [3]
    earlier = await ws.read(threads={one.id}, last=5, before_seq=tail[0].seq)
    assert [e.seq for e in earlier] == [1]
    assert [e.seq for e in await ws.read(after_seq=1, before_seq=4, limit=1)] == [2]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"limit": 1, "last": 1}, "give limit or last, not both"),
        ({"after_seq": -1}, "after_seq cannot be negative"),
        ({"before_seq": -1}, "before_seq cannot be negative"),
        ({"limit": -1}, "limit cannot be negative"),
        ({"last": -1}, "last cannot be negative"),
        ({"after_seq": 2**63}, f"after_seq cannot be more than {2**63 - 1}"),  # PostgreSQL's
    ],
)
async def test_a_read_takes_limit_or_last_and_numbers_storage_holds(
    ws: Workspace, options: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationFailed, match=message):
        await ws.read(**options)


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


async def test_a_workspace_opens_only_if_authorize_allows_it(storage: Storage) -> None:
    opened: list[tuple[str, str]] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        return workspace_id != "secret"

    async def on_open(tenant_id: str, workspace_id: str) -> None:
        opened.append((tenant_id, workspace_id))

    workspaces = Workspaces(storage, authorize=authorize, on_open=on_open)
    assert await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    with pytest.raises(Forbidden, match="artifactr:open is refused in this workspace"):
        await workspaces.open("tenant_a", "secret", actor=ALICE)
    assert opened == [("tenant_a", "ws_1")], "on_open is called on every allowed open only"


async def test_every_method_asks_authorize_as_its_handles_actor(storage: Storage) -> None:
    refused = {"artifactr:read_threads"}
    asked: list[tuple[str, str]] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        asked.append((actor.participant, access.action))
        return access.action not in refused

    ws = await Workspaces(storage, authorize=authorize).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    with pytest.raises(Forbidden, match="artifactr:read_threads is refused in this workspace"):
        await ws.threads()
    agent = AgentActor(thread_id=thread.id, on_behalf_of=ALICE)
    await ws.as_actor(agent).post_message(thread.id, "hi")
    assert asked == [
        ("user:alice", "artifactr:open"),
        ("user:alice", "artifactr:create_thread"),
        ("user:alice", "artifactr:read_threads"),
        (agent.participant, "artifactr:post_message"),
    ]


async def test_a_tenants_workspaces_are_listed_by_those_the_actor_may_open(
    storage: Storage,
) -> None:
    asked: list[tuple[str | None, str]] = []
    opened: list[str] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        asked.append((workspace_id, access.action))
        return workspace_id is None or not workspace_id.startswith("secret")

    async def on_open(tenant_id: str, workspace_id: str) -> None:
        opened.append(workspace_id)

    everyone = Workspaces(storage)
    for workspace_id in ("a", "b", "secret_1", "secret_2", "c", "d"):
        await (await everyone.open("tenant_a", workspace_id, actor=ALICE)).create_thread()
    workspaces = Workspaces(storage, authorize=authorize, on_open=on_open)
    assert await workspaces.list("tenant_a", actor=ALICE, limit=2) == ["a", "b"]
    assert asked == [
        (None, "artifactr:read_workspaces"),
        ("a", "artifactr:open"),
        ("b", "artifactr:open"),
    ]
    page = await workspaces.list("tenant_a", actor=ALICE, after="b", limit=2)
    assert page == ["c", "d"], "a page is filled past the workspaces refused"
    assert await workspaces.list("tenant_a", actor=ALICE, after="d") == []
    assert opened == [], "listing opens nothing"
    assert await everyone.list("tenant_a", actor=ALICE) == [
        "a",
        "b",
        "c",
        "d",
        "secret_1",
        "secret_2",
    ]


async def test_listing_reads_storage_a_page_at_a_time_whatever_the_limit(storage: Storage) -> None:
    workspaces = Workspaces(storage)
    for workspace_id in ("a", "b"):
        await (await workspaces.open("tenant_a", workspace_id, actor=ALICE)).create_thread()
    assert await workspaces.list("tenant_a", actor=ALICE, limit=2**110) == ["a", "b"]


async def test_listing_workspaces_is_asked_with_no_workspace(storage: Storage) -> None:
    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        return workspace_id is not None

    workspaces = Workspaces(storage, authorize=authorize)
    with pytest.raises(Forbidden, match="artifactr:read_workspaces is refused in this tenant"):
        await workspaces.list("tenant_a", actor=ALICE)
    with pytest.raises(ValidationFailed, match="limit must be at least 1"):
        await Workspaces(storage).list("tenant_a", actor=ALICE, limit=0)


async def test_a_thread_is_claimed_by_one_run_at_a_time(ws: Workspace) -> None:
    thread = await ws.create_thread()
    async with ws.claim_thread(thread.id, holder="run_1"):
        with pytest.raises(ThreadBusy):
            async with ws.claim_thread(thread.id, holder="run_2"):
                pass
    async with ws.claim_thread(thread.id, holder="run_2"):
        pass


async def test_a_write_fenced_by_a_claim_is_refused_once_another_holder_has_the_thread(
    storage_factory: StorageFactory,
) -> None:
    now = datetime(2026, 10, 16, tzinfo=UTC)
    ws = await Workspaces(storage_factory(lambda: now)).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    fence = (thread.id, "run_1")
    ttl = timedelta(minutes=1)
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl):
        await ws.commit(PostMessage(thread_id=thread.id, content="Held"), claim=fence)
        now += ttl  # it lapses in storage, before its holder's own timer finds it lost
        async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
            head = await ws.head_seq()
            with pytest.raises(ThreadBusy):
                await ws.commit(PostMessage(thread_id=thread.id, content="Late"), claim=fence)
            agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
            with pytest.raises(ThreadBusy):
                await agent.record(RunStarted(run_id="run_1", thread_id=thread.id), claim=fence)
            assert await ws.head_seq() == head, "nothing is written"


async def test_a_claim_cancelled_as_storage_grants_it_is_released(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await Workspaces(storage).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    acquire = storage.acquire_lease

    async def granted_then_cancelled(*args: Any) -> bool:
        await acquire(*args)
        raise asyncio.CancelledError  # as SQL storage raises once its call has run to its end

    monkeypatch.setattr(storage, "acquire_lease", granted_then_cancelled)
    with pytest.raises(asyncio.CancelledError):
        async with ws.claim_thread(thread.id, holder="run_1"):
            pytest.fail("a cancelled claim is not held")
    monkeypatch.setattr(storage, "acquire_lease", acquire)
    async with ws.claim_thread(thread.id, holder="run_2"):
        pass


async def test_a_claim_is_renewed_while_held(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = await Workspaces(storage).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    acquired: list[str] = []
    renewed = asyncio.Event()
    acquire = storage.acquire_lease

    async def watched(scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        kept = await acquire(scope, key, holder, ttl)
        acquired.append(holder)
        if acquired.count("run_1") == 2:  # the claim, then its first renewal
            renewed.set()
        return kept

    monkeypatch.setattr(storage, "acquire_lease", watched)
    ttl = timedelta(seconds=10)  # renewed every ttl/3
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl) as lost:
        async with asyncio.timeout(5):
            await renewed.wait()
        with pytest.raises(ThreadBusy):
            async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
                pass
        assert not lost.is_set()


async def test_a_claim_renewal_that_fails_is_logged_and_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = Partitioned()
    ws = await Workspaces(storage).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    ttl = timedelta(seconds=1)
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl) as lost:
        storage.cut_off.add("run_1")
        async with asyncio.timeout(5):
            await storage.reached.wait()
        storage.heal()  # the next renewal, a third of the ttl later, keeps the claim
        await asyncio.sleep(1.2)  # longer than the ttl: only a later renewal keeps the claim
        with pytest.raises(ThreadBusy):
            async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
                pass
        assert not lost.is_set()
    assert f"renewing the claim thread:{thread.id} failed; retrying" in caplog.text


async def test_a_claim_that_lapsed_is_lost_once_another_holder_has_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = datetime(2026, 9, 30, tzinfo=UTC)
    ws = await Workspaces(InMemoryStorage(clock=lambda: now)).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    ttl = timedelta(milliseconds=300)
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl) as lost:
        now += ttl  # the lease lapses in storage
        async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
            async with asyncio.timeout(5):
                await lost.wait()
    assert f"the claim thread:{thread.id} lapsed, so it is lost" in caplog.text


async def test_a_claim_not_renewed_for_a_whole_ttl_is_lost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = Partitioned()
    ws = await Workspaces(storage).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    ttl = timedelta(milliseconds=300)
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl) as lost:
        storage.cut_off.add("run_1")  # every renewal fails, though no other holder takes it
        async with asyncio.timeout(5):
            await lost.wait()
        asked = storage.asked["run_1"]
        storage.heal()
        await asyncio.sleep(ttl.total_seconds() / 2)  # past when the next renewal was due
        assert storage.asked["run_1"] == asked, "a lost claim is not renewed"
    assert f"the claim thread:{thread.id} lapsed, so it is lost" in caplog.text


async def test_a_claim_is_lost_at_its_deadline_while_a_renewal_hangs() -> None:
    storage = Partitioned(in_flight=True)
    ws = await Workspaces(storage).open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread()
    ttl = timedelta(milliseconds=300)
    async with ws.claim_thread(thread.id, holder="run_1", ttl=ttl) as lost:  # it ignores lost
        storage.cut_off.add("run_1")
        async with asyncio.timeout(5):
            await storage.reached.wait()
            await lost.wait()
        asked = storage.asked["run_1"]
        storage.heal()
        await asyncio.sleep(0)  # the renewal in flight goes through, taking the lease back
        with pytest.raises(ThreadBusy):
            async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
                pass
        await asyncio.sleep(ttl.total_seconds() / 2)  # past when the next renewal was due
        assert storage.asked["run_1"] == asked, "a lost claim is not renewed"
    async with ws.claim_thread(thread.id, holder="run_2", ttl=ttl):
        pass  # leaving the block released the lease


def test_subclassing_artifact_is_all_it_takes() -> None:
    assert issubclass(Note, Artifact)


async def test_feedback_is_recorded_in_the_log_of_its_thread(ws: Workspace) -> None:
    one, two = await ws.create_thread("one"), await ws.create_thread("two")
    agent = ws.as_actor(AgentActor(thread_id=one.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=one.id))
    await ws.create(Note(text="Ship"), artifact_id="n1")
    judge = ws.as_actor(EvaluatorActor(name="judge", version="v1"))
    rated = await judge.commit(
        GiveFeedback(
            feedback_type="helpfulness", target=TurnTarget(run_id="run_1"), value={"rating": 4}
        )
    )
    assert rated == Recorded(seq=5)
    await ws.commit(
        GiveFeedback(
            feedback_type="accuracy",
            target=ArtifactTarget(artifact_id="n1", version=1),
            value={"correct": True},
        )
    )
    await ws.commit(
        GiveFeedback(
            feedback_type="helpfulness", target=ThreadTarget(thread_id=two.id), value={"rating": 1}
        )
    )
    turn, artifact, thread = await ws.read(after_seq=4)
    assert isinstance(turn.event, FeedbackGiven)
    assert (turn.thread_id, turn.run_id, turn.actor) == (one.id, "run_1", judge.actor)
    assert turn.event.value == {"rating": 4, "reason": None}
    assert artifact.thread_id is None, "feedback on an artifact is workspace-scoped"
    followers_of_one = await ws.read(after_seq=4, threads={one.id})
    assert followers_of_one == [turn, artifact]
    assert thread.thread_id == two.id


NUL = "a\x00b"

type NulCall = Callable[[Workspaces, Workspace], Awaitable[object]]


async def _claim_with_nul(workspaces: Workspaces, ws: Workspace) -> None:
    async with ws.claim_thread("thr_1", holder=NUL):
        pass


async def _as_actor_with_nul(workspaces: Workspaces, ws: Workspace) -> None:
    ws.as_actor(UserActor(id=NUL))


NUL_CALLS: dict[str, NulCall] = {
    "open: tenant": lambda w, ws: w.open(NUL, "ws_1", actor=ALICE),
    "open: workspace": lambda w, ws: w.open("tenant_a", NUL, actor=ALICE),
    "open: actor": lambda w, ws: w.open("tenant_a", "ws_1", actor=UserActor(id=NUL)),
    "list: tenant": lambda w, ws: w.list(NUL, actor=ALICE),
    "list: after": lambda w, ws: w.list("tenant_a", actor=ALICE, after=NUL),
    "as_actor": _as_actor_with_nul,
    "commit: text": lambda w, ws: ws.commit(CreateThread(title=NUL)),
    "commit: cursor": lambda w, ws: ws.commit(CreateThread(), cursor=(NUL, 1)),
    "create": lambda w, ws: ws.create(Note(text=NUL)),
    "create_thread": lambda w, ws: ws.create_thread(NUL),
    "post_message": lambda w, ws: ws.post_message("thr_1", NUL),
    "record: data": lambda w, ws: ws.record(AppEvent(name="noted", data={"note": [NUL]})),
    "record: cursor": lambda w, ws: ws.record(AppEvent(name="noted"), cursor=(NUL, 1)),
    "get": lambda w, ws: ws.get(Note, NUL),
    "artifact": lambda w, ws: ws.artifact(NUL),
    "artifacts": lambda w, ws: ws.artifacts(kind=NUL),
    "revisions": lambda w, ws: ws.revisions(NUL),
    "thread": lambda w, ws: ws.thread(NUL),
    "proposal": lambda w, ws: ws.proposal(NUL),
    "run": lambda w, ws: ws.run(NUL),
    "runs": lambda w, ws: ws.runs(thread_id=NUL),
    "history": lambda w, ws: ws.history(NUL),
    "read": lambda w, ws: ws.read(threads=[NUL]),
    "subscribe": lambda w, ws: anext(aiter(ws.subscribe(threads=[NUL]))),
    "change_notes": lambda w, ws: ws.change_notes(after_seq=0, focus={NUL}),
    "cursor": lambda w, ws: ws.cursor(NUL),
    "save_cursor": lambda w, ws: ws.save_cursor(NUL, 1),
    "claim_thread": _claim_with_nul,
}
"""Each way a string reaches a workspace, with a NUL character in it (ADR-0061), named by the
method it reaches, and what it is when a method takes more than one."""

TEXTLESS = {
    "check": "takes an Access, which every other method builds from text already checked",
    "head_seq": "takes nothing",
    "hidden": "takes nothing",
    "threads": "takes nothing",
    "proposals": "takes a status, one of a few literals",
}
"""Public methods that take no text of their own, and why."""


def test_every_public_method_that_takes_text_refuses_a_nul() -> None:
    public = {
        name
        for cls in (Workspaces, Workspace)
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_") and inspect.isfunction(member)
    }
    assert {call.split(":")[0] for call in NUL_CALLS} | set(TEXTLESS) == public


@pytest.mark.parametrize("call", sorted(NUL_CALLS))
async def test_a_nul_character_is_refused_before_authorize_hears_it(
    storage: Storage, call: str
) -> None:
    asked: list[str] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        asked.append(access.action)
        return True

    workspaces = Workspaces(storage, authorize=authorize)
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    asked.clear()
    with pytest.raises(ValidationFailed, match="text cannot hold a NUL character"):
        await NUL_CALLS[call](workspaces, ws)
    assert asked == []
    assert await workspaces.list("tenant_a", actor=ALICE) == [], "nothing was written"
