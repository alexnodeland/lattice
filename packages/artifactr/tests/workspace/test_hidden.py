"""Restricted threads and artifacts (lattice RFC-0001's phase 5): every read leaves them out.

Alice sees everything; the ``hidden`` hook hides a thread and an artifact from Bob, and from an
agent acting for him. Each read path is called as Bob, over every storage.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta

import pytest
from opentelemetry.sdk.trace import TracerProvider
from pydantic import JsonValue

from artifactr.core import (
    Actor,
    AgentActor,
    AnswerDeferred,
    AppEvent,
    ArtifactCreated,
    ArtifactTarget,
    CreateThread,
    Envelope,
    FocusChanged,
    GiveFeedback,
    MessageTarget,
    NotFound,
    ProposeChange,
    Rejection,
    RespondToProposal,
    RunStarted,
    SetFocus,
    TenantId,
    TurnTarget,
    UserActor,
    Visibility,
    WorkspaceId,
    acting_for,
)
from artifactr.workspace import Storage, Workspace, Workspaces
from tests.artifact_types import Note
from tests.test_access import METHODS

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")
OPEN, CLOSED = "thr_open", "thr_closed"
SHARED, RESTRICTED, FROM_CLOSED = "a_shared", "a_restricted", "a_from_closed"
ON_RESTRICTED, FROM_CLOSED_PROPOSAL = "prp_restricted", "prp_closed"
CLOSED_RUN = "run_closed"


class Hider:
    """A ``hidden`` hook that hides what it is told from Bob, and from agents acting for him."""

    def __init__(self) -> None:
        self.from_bob = Visibility(threads=frozenset({CLOSED}), artifacts=frozenset({RESTRICTED}))
        self.asked = 0

    async def __call__(
        self, tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor
    ) -> Visibility:
        self.asked += 1
        return self.from_bob if acting_for(actor) == BOB else Visibility()


@pytest.fixture
def hider() -> Hider:
    return Hider()


@pytest.fixture
async def bob(storage: Storage, hider: Hider) -> Workspace:
    """Bob's handle on a workspace Alice has filled: each kind of item, seen and hidden."""
    workspaces = Workspaces(storage, types=[Note], hidden=hider)
    alice = await workspaces.open("acme", "w1", actor=ALICE)
    for thread in (OPEN, CLOSED):
        await alice.commit(CreateThread(thread_id=thread))
    await alice.create(Note(text="shared"), artifact_id=SHARED)
    await alice.create(Note(text="restricted"), artifact_id=RESTRICTED)
    await alice.create(
        Note(text="from the closed thread"), artifact_id=FROM_CLOSED, thread_id=CLOSED
    )
    await alice.commit(SetFocus(thread_id=OPEN, artifact_ids=(SHARED, RESTRICTED)))
    agent = alice.as_actor(AgentActor(thread_id=CLOSED, run_id=CLOSED_RUN))
    await agent.record(RunStarted(run_id=CLOSED_RUN, thread_id=CLOSED))
    await alice.record(AppEvent(name="noted", thread_id=CLOSED), history=b'[{"kind":"request"}]')
    shared = await alice.get(Note, SHARED)
    await agent.commit(shared.edit_text("shared", "shared, edited in the closed thread"))
    for proposal, artifact in ((ON_RESTRICTED, RESTRICTED), (FROM_CLOSED_PROPOSAL, SHARED)):
        edit = (await alice.get(Note, artifact)).edit_text(artifact.removeprefix("a_"), "x")
        change = edit.model_copy(update={"thread_id": CLOSED})
        await agent.commit(ProposeChange(proposal_id=proposal, change=change))
    await alice.commit(RespondToProposal(proposal_id=FROM_CLOSED_PROPOSAL, decision="accept"))
    target = ArtifactTarget(artifact_id=RESTRICTED, version=1)
    await alice.commit(
        GiveFeedback(feedback_type="accuracy", target=target, value={"correct": True})
    )
    return alice.as_actor(BOB)


def _about_hidden(envelope: Envelope) -> bool:
    text = envelope.model_dump_json()
    return CLOSED in text or RESTRICTED in text or CLOSED_RUN in text


# ─── one test per read path ──────────────────────────────────────────────────

Call = Callable[[Workspace, str], Awaitable[object]]

AS_MISSING: dict[str, tuple[Call, str, str]] = {
    "get": (lambda ws, a: ws.get(Note, a), RESTRICTED, "a_none"),
    "artifact": (lambda ws, a: ws.artifact(a), RESTRICTED, "a_none"),
    "revisions": (lambda ws, a: ws.revisions(a), RESTRICTED, "a_none"),
    "thread": (lambda ws, t: ws.thread(t), CLOSED, "thr_none"),
    "proposal": (lambda ws, p: ws.proposal(p), ON_RESTRICTED, "prp_none"),
    "run": (lambda ws, r: ws.run(r), CLOSED_RUN, "run_none"),
    "runs": (lambda ws, t: ws.runs(thread_id=t), CLOSED, "thr_none"),
    "history": (lambda ws, t: ws.history(t), CLOSED, "thr_none"),
    "commit": (lambda ws, t: ws.post_message(t, "hello?"), CLOSED, "thr_none"),
    "respond_to_proposal": (
        lambda ws, p: ws.commit(RespondToProposal(proposal_id=p, decision="reject")),
        ON_RESTRICTED,
        "prp_none",
    ),
    "answer_deferred": (
        lambda ws, r: ws.commit(AnswerDeferred(run_id=r, tool_call_id="q1")),
        CLOSED_RUN,
        "run_none",
    ),
    "feedback_on_a_turn": (
        lambda ws, r: ws.commit(
            GiveFeedback(feedback_type="helpfulness", target=TurnTarget(run_id=r), value=RATED)
        ),
        CLOSED_RUN,
        "run_none",
    ),
    "feedback_on_a_message": (
        lambda ws, r: ws.commit(
            GiveFeedback(
                feedback_type="helpfulness",
                target=MessageTarget(thread_id=OPEN, message_id="m1", run_id=r),
                value=RATED,
            )
        ),
        CLOSED_RUN,
        "run_none",
    ),
    "set_focus": (
        lambda ws, a: ws.commit(SetFocus(thread_id=OPEN, artifact_ids=(a,))),
        RESTRICTED,
        "a_none",
    ),
}
"""A read, or a command, of a hidden item, and of one that doesn't exist, with the id each
names: each answers alike, naming nothing but the id it was given."""

RATED: dict[str, JsonValue] = {"rating": 4}

HIDDEN_IDS = {RESTRICTED, CLOSED, CLOSED_RUN, ON_RESTRICTED}


async def _outcome(call: Call, ws: Workspace, id: str) -> object:
    """What a call answers: its value, or its rejection, with ``id`` standing for its own id."""
    try:
        return await call(ws, id)
    except Rejection as rejection:
        refused = rejection
    if refused.payload().get("type") == "not_found":  # what Bob is answered
        named = [hidden for hidden in HIDDEN_IDS | {id} if hidden in refused.message]
        assert named in ([], [id]), f"{refused.message} names more than {id}"
    return {k: "<id>" if v == id else v for k, v in refused.payload().items() if k != "message"}


@pytest.mark.parametrize("method", sorted(AS_MISSING))
async def test_a_hidden_item_answers_as_a_missing_one(bob: Workspace, method: str) -> None:
    call, hidden, made_up = AS_MISSING[method]
    assert await _outcome(call, bob, hidden) == await _outcome(call, bob, made_up)
    assert await _outcome(call, bob.as_actor(ALICE), hidden) != await _outcome(call, bob, hidden)


REFUSED: dict[str, Callable[[Workspace], Awaitable[object]]] = {
    "record": lambda ws: ws.as_actor(
        AgentActor(thread_id=CLOSED, run_id="run_2", on_behalf_of=BOB)
    ).record(RunStarted(run_id="run_2", thread_id=CLOSED)),
    "claim_thread": lambda ws: _claim(ws, CLOSED),
}
"""The runner's own work on a hidden thread, for an agent acting for Bob: not found."""


async def _claim(ws: Workspace, thread: str) -> None:
    async with ws.claim_thread(thread, holder="h", ttl=timedelta(seconds=5)):
        pass


@pytest.mark.parametrize("method", sorted(REFUSED))
async def test_the_runners_work_on_a_hidden_thread_is_not_found(
    bob: Workspace, method: str
) -> None:
    with pytest.raises(NotFound):
        await REFUSED[method](bob)


async def test_listings_leave_hidden_items_out(bob: Workspace) -> None:
    assert [a.id for a in await bob.artifacts()] == [SHARED, FROM_CLOSED]
    assert CLOSED not in (await bob.artifact(SHARED)).model_dump_json()
    assert CLOSED not in str([a.model_dump_json() for a in await bob.artifacts()])
    assert CLOSED not in str([r.model_dump_json() for r in await bob.revisions(SHARED)])
    assert [t.id for t in await bob.threads()] == [OPEN]
    assert (await bob.thread(OPEN)).focus == (SHARED,)
    assert [t.focus for t in await bob.threads()] == [(SHARED,)]
    assert await bob.runs() == []
    [proposal] = await bob.proposals(status=None)
    assert proposal.id == FROM_CLOSED_PROPOSAL
    assert CLOSED not in proposal.model_dump_json()
    assert await bob.proposal(FROM_CLOSED_PROPOSAL) == proposal


async def test_the_log_drops_hidden_items_and_where_an_artifact_came_from(bob: Workspace) -> None:
    log = await bob.read()
    assert not [e for e in log if _about_hidden(e)]
    [created] = [
        e
        for e in log
        if isinstance(e.event, ArtifactCreated) and e.event.artifact_id == FROM_CLOSED
    ]
    assert created.thread_id is None
    assert [e.event.artifact_ids for e in log if isinstance(e.event, FocusChanged)] == [(SHARED,)]
    assert [e.seq for e in log] == [e.seq async for e in _replay(bob, len(log))]
    assert not [n for n in await bob.change_notes(after_seq=0) if RESTRICTED in n.model_dump_json()]


async def _replay(ws: Workspace, count: int) -> AsyncIterator[Envelope]:
    stream = aiter(ws.subscribe())
    for _ in range(count):
        yield await anext(stream)


async def test_a_page_of_the_log_is_full_whatever_was_hidden(bob: Workspace) -> None:
    everything = await bob.read()
    for size in (1, 2, 3):
        pages: list[list[Envelope]] = []
        after = 0
        while page := await bob.read(after_seq=after, limit=size):
            assert len(page) == size or page[-1] == everything[-1]
            pages.append(page)
            after = page[-1].seq
        assert [e for page in pages for e in page] == everything
        backwards: list[Envelope] = []
        before = None
        while page := await bob.read(before_seq=before, last=size):
            backwards = page + backwards
            before = page[0].seq
        assert backwards == everything
    assert await bob.read(limit=0) == []


async def test_alice_sees_everything(bob: Workspace) -> None:
    alice = bob.as_actor(ALICE)
    assert len(await alice.threads()) == 2
    assert await alice.read(limit=1) == (await alice.read())[:1]


async def test_an_open_stream_learns_of_a_restriction_at_its_refresh(
    storage: Storage, hider: Hider
) -> None:
    workspaces = Workspaces(storage, types=[Note], hidden=hider, hidden_refresh=timedelta(0))
    alice = await workspaces.open("acme", "w1", actor=ALICE)
    stream = aiter(alice.as_actor(BOB).subscribe())
    await alice.commit(CreateThread(thread_id=CLOSED))
    await alice.commit(CreateThread(thread_id=OPEN))
    assert (await anext(stream)).thread_id == OPEN
    hider.from_bob = Visibility()
    await alice.post_message(CLOSED, "now Bob may read this")
    assert (await anext(stream)).thread_id == CLOSED


COMMANDS = {
    "respond_to_proposal",
    "answer_deferred",
    "feedback_on_a_turn",
    "feedback_on_a_message",
    "set_focus",
}
"""Commands tested above, which ``commit`` carries out."""

LISTINGS = {"artifacts", "threads", "proposals", "runs", "read", "subscribe", "change_notes"}
"""The reads that leave hidden items out, tested above."""

UNFILTERED = {
    "head_seq": "a number, about no item",
    "cursor": "a consumer's own position in the log",
    "create": "a new artifact: an id already restricted answers missing, where one in use"
    " answers a conflict, but ids are random",
    "create_thread": "a new thread, which no one has restricted",
    "post_message": "asks for its thread, as commit does",
    "save_cursor": "a consumer's own position in the log",
}
"""``Workspace`` methods with nothing to leave out, or that ask as one listed does, and why."""


def test_every_workspace_method_is_tested_for_what_it_hides() -> None:
    assert set(METHODS) == {*AS_MISSING, *REFUSED} - COMMANDS | LISTINGS | set(UNFILTERED)


async def test_a_focus_keeps_what_its_setter_cant_see(bob: Workspace) -> None:
    await bob.commit(SetFocus(thread_id=OPEN, artifact_ids=(FROM_CLOSED,)))
    assert (await bob.thread(OPEN)).focus == (FROM_CLOSED,)
    assert (await bob.as_actor(ALICE).thread(OPEN)).focus == (FROM_CLOSED, RESTRICTED)


async def test_nothing_kept_names_a_hidden_threads_trace(bob: Workspace) -> None:
    alice = bob.as_actor(ALICE)
    agent = alice.as_actor(AgentActor(thread_id=CLOSED, run_id=CLOSED_RUN))
    with TracerProvider().get_tracer("test").start_as_current_span("closed turn"):
        shared = await alice.get(Note, SHARED)
        await agent.commit(shared.edit_text("x", "y"))
    [*_, theirs] = await alice.revisions(SHARED)
    assert theirs.trace_id is not None
    [*_, seen] = await bob.revisions(SHARED)
    assert (seen.trace_id, seen.version) == (None, theirs.version)
    kept = [e for e in await bob.read() if e.event.type == "artifact_changed"]
    assert kept
    assert all(e.traceparent is None for e in kept if e.actor.kind == "agent")


async def test_a_handle_asks_once_per_refresh(bob: Workspace, hider: Hider) -> None:
    asked = hider.asked
    await bob.threads()
    await bob.artifacts()
    assert hider.asked == asked + 1, "a request asks once"
