"""The followers, over both libraries' in-memory storage and every ledger.

Phase 1's exit criterion is here: an artifactr message fires a reflexr rule exactly once, across a
restart and a redelivery.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

import artifactr
import artifactr.core as a
import artifactr.workspace
import reflexr
import reflexr.workspace as r
from relayr.events import BRIDGED, MessagePosted, Projections, TurnEnded
from relayr.inbound import FOLLOWER, SOURCE, Followers, followers
from relayr.ledger import DeadLetter, Ledger, WorkspaceKey
from tests.app_types import Note
from tests.clock import FakeClock

type Access = artifactr.workspace.Access | r.Access

TENANT, WORKSPACE = "acme", "prod"
KEY = WorkspaceKey(TENANT, WORKSPACE)
ALICE = a.UserActor(id="alice")
TTL = timedelta(milliseconds=60)

GREET = reflexr.Rule(
    name="app:greet",
    when=reflexr.on(MessagePosted).where(reflexr.F.author.kind.eq("user")),
    then=reflexr.run("greet"),
)


@dataclass
class Process:
    """One process of an application: both libraries, the followers and a reactor."""

    collaboration: artifactr.Workspaces
    automation: r.Workspaces
    followers: Followers
    reactor: r.Reactor[None]

    async def post(self, content: str) -> a.Recorded:
        """Post a message as Alice, opening the workspace as people do."""
        return await post(self.collaboration, content)


async def post(collaboration: artifactr.Workspaces, content: str) -> a.Recorded:
    """Post a message as Alice, in a thread of its own."""
    workspace = await collaboration.open(TENANT, WORKSPACE, actor=ALICE)
    thread = await workspace.create_thread()
    return await workspace.post_message(thread.id, content)


def at(outcome: a.Recorded | a.Applied | a.Proposed) -> int:
    """Where in artifactr's log a command's last event is."""
    assert outcome.seq is not None
    return outcome.seq


@dataclass
class Stack:
    """What outlives a process: the libraries' storage, and what the rule's runs did."""

    artifactr_storage: artifactr.InMemoryStorage = field(default_factory=artifactr.InMemoryStorage)
    reflexr_storage: r.InMemoryStorage = field(default_factory=r.InMemoryStorage)
    greeted: list[str] = field(default_factory=list[str])
    processes: list[Process] = field(default_factory=list[Process])

    async def bridged(self) -> list[reflexr.Envelope]:
        """The bridged envelopes in reflexr's log, read past the followers."""
        reader = r.Workspaces(self.reflexr_storage)
        workspace = await reader.open(TENANT, WORKSPACE, actor=reflexr.SystemActor())
        return [e for e in await workspace.read() if e.event_type.startswith("artifactr:")]

    async def log(self) -> list[a.Envelope]:
        """artifactr's log, read past the followers."""
        reader = artifactr.Workspaces(self.artifactr_storage)
        return await (await reader.open(TENANT, WORKSPACE, actor=ALICE)).read()

    def process(
        self,
        ledger: Ledger,
        *,
        holder: str = "p1",
        projections: Projections | None = None,
        events: tuple[type[reflexr.Event], ...] = BRIDGED,
        authorize: r.Authorize | None = None,
        artifactr_authorize: artifactr.workspace.Authorize | None = None,
    ) -> Process:
        async def on_open(tenant_id: str, workspace_id: str) -> None:
            await bridge.watch(tenant_id, workspace_id)

        async def greet(reaction: r.Reaction[None]) -> None:
            [envelope] = reaction.events
            self.greeted.append(envelope.event.model_dump()["content"])

        collaboration = artifactr.Workspaces(
            self.artifactr_storage, authorize=artifactr_authorize, on_open=on_open
        )
        automation = r.Workspaces(
            self.reflexr_storage,
            events=events,
            rules=[GREET],
            authorize=authorize,
            on_open=on_open,
        )
        bridge = Followers(
            collaboration,
            automation,
            ledger,
            projections=projections,
            holder=holder,
            lease_ttl=TTL,
        )
        reactor = r.Reactor(automation, actions={"greet": greet})
        process = Process(collaboration, automation, bridge, reactor)
        self.processes.append(process)
        return process


@pytest.fixture
async def stack() -> AsyncIterator[Stack]:
    """The storage processes share; every process's followers stop when the test ends."""
    shared = Stack()
    yield shared
    for process in shared.processes:
        await process.followers.aclose()


async def until(check: Callable[[], Awaitable[bool]]) -> None:
    for _ in range(300):
        if await check():
            return
        await asyncio.sleep(0.01)
    pytest.fail("it never happened")


async def bridged(stack: Stack, count: int) -> None:
    async def done() -> bool:
        return len(await stack.bridged()) >= count

    await until(done)


class Forgetful:
    """A ledger that saves no cursor: its process stops after publishing, before each save."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    async def acquire_lease(self, workspace: WorkspaceKey, holder: str, ttl: timedelta) -> bool:
        return await self._ledger.acquire_lease(workspace, holder, ttl)

    async def release_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        await self._ledger.release_lease(workspace, holder)

    async def cursor(self, workspace: WorkspaceKey) -> int:
        return await self._ledger.cursor(workspace)

    async def save_cursor(self, workspace: WorkspaceKey, seq: int) -> None:
        return None

    async def dead_letter(self, workspace: WorkspaceKey, letter: DeadLetter) -> None:
        await self._ledger.dead_letter(workspace, letter)

    async def dead_letters(self, workspace: WorkspaceKey) -> list[DeadLetter]:
        return await self._ledger.dead_letters(workspace)

    async def followed(self) -> list[WorkspaceKey]:
        return await self._ledger.followed()


async def test_a_message_fires_a_rule_exactly_once_across_a_restart_and_a_redelivery(
    ledger: Ledger, stack: Stack
) -> None:
    # The first process bridges the message, but stops before it saves its cursor.
    first = stack.process(Forgetful(ledger), holder="p1")
    posted = at(await first.post("hello"))
    await bridged(stack, 1)
    await first.reactor.settle()
    await first.followers.aclose()
    assert stack.greeted == ["hello"]
    assert await ledger.cursor(KEY) == 0

    # The second resumes the workspace from the ledger, and delivers the message again.
    second = stack.process(ledger, holder="p2")
    await second.followers.resume()

    async def caught_up() -> bool:
        return await ledger.cursor(KEY) == posted

    await until(caught_up)
    await second.reactor.settle()
    assert stack.greeted == ["hello"], "the message, delivered again, fired nothing"

    # The restarted follower bridges what comes next, once.
    again = at(await second.post("again"))
    await bridged(stack, 2)
    await second.reactor.settle()
    await second.followers.aclose()
    assert stack.greeted == ["hello", "again"]
    [hello, later] = await stack.bridged()
    log = {e.seq: e for e in await stack.log()}
    assert (hello.id, later.id) == (log[posted].id, log[again].id)
    assert hello.actor == SOURCE
    assert isinstance(hello.event, MessagePosted)
    assert (hello.event.author, hello.event.content) == (ALICE, "hello")


def refuse_notes(envelope: a.Envelope) -> reflexr.Event | None:
    raise ValueError("no notes")


async def test_an_envelope_that_cannot_be_bridged_is_dead_lettered(
    ledger: Ledger, stack: Stack
) -> None:
    app = stack.process(
        ledger,
        projections=Projections(artifacts={"note": refuse_notes}),
        events=tuple(t for t in BRIDGED if t is not TurnEnded),
    )
    workspace = await app.collaboration.open(TENANT, WORKSPACE, actor=ALICE)
    thread = await workspace.create_thread()
    agent = workspace.as_actor(a.AgentActor(thread_id=thread.id, run_id="run_1"))
    created = at(await workspace.create(Note(text="notes")))
    await agent.record(a.RunStarted(run_id="run_1", thread_id=thread.id))
    ended = at(
        await agent.record(a.RunEnded(run_id="run_1", thread_id=thread.id, status="completed"))
    )
    posted = at(await workspace.post_message(thread.id, "after"))

    async def caught_up() -> bool:
        return await ledger.cursor(KEY) == posted

    await until(caught_up)
    await app.followers.aclose()
    log = {e.seq: e for e in await stack.log()}
    assert await ledger.dead_letters(KEY) == [
        DeadLetter(
            seq=created,
            envelope_id=log[created].id,
            event_type="artifact_created",
            error="ValueError: no notes",
        ),
        DeadLetter(
            seq=ended,
            envelope_id=log[ended].id,
            event_type="run_ended",
            error="NotFound: event type artifactr:turn_ended does not exist",
        ),
    ]
    assert [e.event_type for e in await stack.bridged()] == ["artifactr:message_posted"]


async def test_a_cursor_is_saved_every_so_many_envelopes_that_bridge_nothing(
    ledger: Ledger, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(followers, "SAVE_EVERY", 3)
    app = stack.process(ledger)
    workspace = await app.collaboration.open(TENANT, WORKSPACE, actor=ALICE)
    for _ in range(4):
        await workspace.create_thread()

    async def saved() -> bool:
        return await ledger.cursor(KEY) == 3

    await until(saved)
    await asyncio.sleep(0.05)
    await app.followers.aclose()
    assert await ledger.cursor(KEY) == 3, "the fourth is read again after a restart"


async def test_one_process_at_a_time_follows_a_workspace(ledger: Ledger, stack: Stack) -> None:
    first = stack.process(ledger, holder="p1")
    second = stack.process(ledger, holder="p2")
    await first.post("one")
    await second.followers.watch(TENANT, WORKSPACE)
    await bridged(stack, 1)
    await first.followers.aclose()  # releasing the lease, which the second takes
    await post(artifactr.Workspaces(stack.artifactr_storage), "two")  # starting no follower
    await bridged(stack, 2)
    await second.followers.aclose()
    assert len(await stack.bridged()) == 2


async def test_a_follower_that_loses_its_lease_stops_until_it_gets_it_back(
    ledger: Ledger, stack: Stack, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    app = stack.process(ledger)
    await app.post("one")
    await bridged(stack, 1)
    with caplog.at_level(logging.INFO, logger="relayr.inbound"):
        while not await ledger.acquire_lease(KEY, "thief", TTL):
            clock.advance(TTL)  # the lease lapses, and a thief takes it

        async def lost() -> bool:
            return "the lease on acme/prod went to another holder" in caplog.text

        await until(lost)
    await app.post("two")
    await asyncio.sleep(0.05)
    assert len(await stack.bridged()) == 1
    await ledger.release_lease(KEY, "thief")
    await bridged(stack, 2)


async def test_a_refused_publish_stops_the_follower_until_the_workspace_is_opened_again(
    ledger: Ledger, stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    refusing = True

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: reflexr.Actor, access: r.Access
    ) -> bool:
        return not (refusing and access.action == "reflexr:publish")

    app = stack.process(ledger, authorize=authorize)
    with caplog.at_level(logging.WARNING, logger="relayr.inbound"):
        await app.post("one")

        async def stopped() -> bool:
            return "following acme/prod stopped" in caplog.text

        await until(stopped)
    assert await stack.bridged() == []
    refusing = False
    await app.post("two")  # opening the workspace starts its follower again
    await bridged(stack, 2)


async def test_the_follower_reads_and_publishes_as_its_own_actors(
    ledger: Ledger, stack: Stack
) -> None:
    seen: set[tuple[str, str]] = set()

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: a.Actor | reflexr.Actor, access: Access
    ) -> bool:
        if actor in (FOLLOWER, SOURCE):
            seen.add((actor.participant, access.action))
        return True

    app = stack.process(ledger, authorize=authorize, artifactr_authorize=authorize)
    await app.post("one")
    await bridged(stack, 1)
    assert seen == {
        ("system:relayr", "artifactr:open"),
        ("system:relayr", "artifactr:read_events"),
        ("source:artifactr", "reflexr:open"),
        ("source:artifactr", "reflexr:publish"),
    }
