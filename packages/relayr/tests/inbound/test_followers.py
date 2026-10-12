"""The followers, over both libraries' in-memory storage and every ledger.

Phase 1's exit criterion is here: an artifactr message fires a reflexr rule exactly once, across a
restart and a redelivery.
"""

import asyncio
import logging
from datetime import timedelta

import pytest

import artifactr
import artifactr.core as a
import artifactr.workspace
import reflexr
import reflexr.workspace as r
from reflexr.core import Tick
from relayr.events import BRIDGED, ArtifactCreated, MessagePosted, Projections
from relayr.inbound import FOLLOWER, SOURCE
from relayr.ledger import Cause, CauseKind, DeadLetter, InMemoryLedger, Ledger, WorkspaceKey
from tests.app_types import Note
from tests.clock import START, FakeClock
from tests.stack import ALICE, KEY, TENANT, TTL, WORKSPACE, Access, Stack, at, bridged, post, until


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

    async def record_cause(
        self, workspace: WorkspaceKey, kind: CauseKind, key: str, cause: Cause
    ) -> None:
        await self._ledger.record_cause(workspace, kind, key, cause)

    async def cause(self, workspace: WorkspaceKey, kind: CauseKind, key: str) -> Cause | None:
        return await self._ledger.cause(workspace, kind, key)

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


def tick(envelope: a.Envelope) -> reflexr.Event:
    return Tick(schedule="forged", at=START)


async def test_an_envelope_that_cannot_be_bridged_is_dead_lettered(
    ledger: Ledger, stack: Stack
) -> None:
    app = stack.process(
        ledger,
        projections=Projections(app_events={"tick": tick}, artifacts={"note": refuse_notes}),
    )
    workspace = await app.collaboration.open(TENANT, WORKSPACE, actor=ALICE)
    thread = await workspace.create_thread()
    created = at(await workspace.create(Note(text="notes")))
    forged = at(await workspace.record(a.AppEvent(name="tick")))
    posted = at(await workspace.post_message(thread.id, "after"))

    async def caught_up() -> bool:
        return await ledger.cursor(KEY) == posted

    await until(caught_up)
    log = {e.seq: e for e in await stack.log()}
    assert await ledger.dead_letters(KEY) == [
        DeadLetter(
            seq=created,
            envelope_id=log[created].id,
            event_type="artifact_created",
            error="ValueError: no notes",
        ),
        DeadLetter(
            seq=forged,
            envelope_id=log[forged].id,
            event_type="app_event",
            error="Forbidden: reflexr:tick events are recorded by reflexr, not published",
        ),
    ]
    assert [e.event_type for e in await stack.bridged()] == ["artifactr:message_posted"]


async def test_a_type_reflexr_does_not_accept_stops_the_follower_at_it(
    ledger: Ledger, stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    app = stack.process(ledger, events=tuple(t for t in BRIDGED if t is not ArtifactCreated))
    with caplog.at_level(logging.ERROR, logger="relayr.inbound"):
        workspace = await app.collaboration.open(TENANT, WORKSPACE, actor=ALICE)
        await workspace.create(Note(text="notes"))

        async def stopped() -> bool:
            return "following acme/prod stopped" in caplog.text

        await until(stopped)
    assert "NotFound: event type artifactr:artifact_created does not exist" in caplog.text
    assert "ExceptionGroup" not in caplog.text
    assert await ledger.dead_letters(KEY) == []
    assert await ledger.cursor(KEY) == 0, "the message is read again once reflexr accepts it"


async def test_closed_followers_follow_nothing_more(ledger: Ledger, stack: Stack) -> None:
    app = stack.process(ledger)
    await app.followers.aclose()
    await app.post("hello")
    await asyncio.sleep(0.05)
    assert await ledger.followed() == []


class Failing(InMemoryLedger):
    """A ledger that can't renew a lease: it fails every acquisition after the first."""

    def __init__(self) -> None:
        super().__init__()
        self.acquired = 0

    async def acquire_lease(self, workspace: WorkspaceKey, holder: str, ttl: timedelta) -> bool:
        self.acquired += 1
        if self.acquired > 1:
            raise ConnectionError("the ledger is down")
        return await super().acquire_lease(workspace, holder, ttl)


async def test_a_failed_renewal_stops_the_follower(
    stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    app = stack.process(Failing())
    with caplog.at_level(logging.ERROR, logger="relayr.inbound"):
        await app.post("hello")

        async def stopped() -> bool:
            return "following acme/prod stopped" in caplog.text

        await until(stopped)
    assert "ConnectionError: the ledger is down" in caplog.text


async def test_a_cursor_is_saved_every_so_many_envelopes_that_bridge_nothing(
    ledger: Ledger, stack: Stack
) -> None:
    app = stack.process(ledger, save_every=3)
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
