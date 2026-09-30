"""The storage contract, below the workspace: transactions, reads, leases and cursors."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from artifactr.core import (
    AppEvent,
    CreateArtifact,
    CreateThread,
    Envelope,
    MessagePosted,
    Needs,
    PostMessage,
    State,
    UserActor,
    commit,
    needs,
)
from artifactr.workspace import Scope, Storage, Workspace, Workspaces
from tests.workspace.conftest import StorageFactory

ALICE = UserActor(id="alice")
SCOPE = Scope("tenant_a", "ws_1")


async def _create_thread(storage: Storage, thread_id: str) -> None:
    command = CreateThread(thread_id=thread_id)
    async with storage.transaction(SCOPE) as tx:
        state = await tx.load(needs(command, actor=ALICE))
        await tx.save(commit(command, state, actor=ALICE), actor=ALICE)


async def test_later_loads_in_a_transaction_see_earlier_saves(storage: Storage) -> None:
    async with storage.transaction(SCOPE) as tx:
        first = CreateThread(thread_id="t1")
        await tx.save(
            commit(first, await tx.load(needs(first, actor=ALICE)), actor=ALICE), actor=ALICE
        )
        loaded = await tx.load(Needs(threads=frozenset({"t1", "t2"})))
        assert loaded.threads["t1"] is not None
        assert loaded.threads["t2"] is None
        envelopes = await tx.save(
            commit(CreateThread(thread_id="t2"), State(threads={"t2": None}), actor=ALICE),
            actor=ALICE,
        )
        assert [e.seq for e in envelopes] == [2], "seq continues within the transaction"
        post = PostMessage(thread_id="t1", message_id="m1", content="hi")
        await tx.save(
            commit(post, await tx.load(needs(post, actor=ALICE)), actor=ALICE), actor=ALICE
        )
        messages = (await tx.load(Needs(messages=frozenset({"m1", "m2"})))).messages
        assert messages == {"m1": True, "m2": False}


async def test_a_transaction_that_raises_rolls_back(storage: Storage) -> None:
    post = PostMessage(thread_id="t1", message_id="m1", content="hi")

    async def save_then_fail() -> None:
        async with storage.transaction(SCOPE) as tx:
            await tx.save(
                commit(CreateThread(thread_id="t1"), State(threads={"t1": None}), actor=ALICE),
                actor=ALICE,
            )
            await tx.save(
                commit(post, await tx.load(needs(post, actor=ALICE)), actor=ALICE), actor=ALICE
            )
            await tx.append_history("t1", b"[]")
            raise RuntimeError("the host failed after saving")

    with pytest.raises(RuntimeError):
        await save_then_fail()
    assert await storage.head_seq(SCOPE) == 0
    assert await storage.thread(SCOPE, "t1") is None
    assert await storage.history(SCOPE, "t1") == []
    async with storage.transaction(SCOPE) as tx:
        assert (await tx.load(Needs(messages=frozenset({"m1"})))).messages == {"m1": False}


async def test_a_transaction_cancelled_at_any_await_leaves_the_workspace_usable(
    storage: Storage,
) -> None:
    # Cancelled after each number of yields in turn, until one ends before its cancellation
    # comes. A hundred at most: a loop that never blocks would starve a driver's thread.
    for yields in range(100):
        task = asyncio.create_task(_create_thread(storage, f"t{yields}"))
        for _ in range(yields):
            await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with asyncio.timeout(1):
            await _create_thread(storage, f"next{yields}")
        if not task.cancelled():
            task.result()
            break
    log = await storage.read(SCOPE)
    assert [e.seq for e in log] == list(range(1, len(log) + 1))
    threads = {thread.id for thread in await storage.threads(SCOPE)}
    assert {e.thread_id for e in log} == threads, "all or nothing"


async def test_reads_filter_and_page(storage: Storage) -> None:
    for thread_id in ("t1", "t2", "t3"):
        await _create_thread(storage, thread_id)
    assert [e.seq for e in await storage.read(SCOPE, after_seq=1, limit=1)] == [2]
    assert await storage.artifacts(SCOPE, kind="note") == []


async def test_reads_take_a_window_for_some_threads_from_its_start_or_its_end(
    storage: Storage, ws: Workspace
) -> None:
    one = await ws.create_thread("one")  # 1
    two = await ws.create_thread("two")  # 2
    await ws.post_message(one.id, "in one")  # 3
    await ws.post_message(two.id, "in two")  # 4
    await ws.commit(CreateArtifact(artifact_id="n1", kind="note", data={}, thread_id=two.id))  # 5
    await ws.record(AppEvent(name="exported"))  # 6: no thread
    await ws.post_message(two.id, "again in two")  # 7

    async def seqs(**options: Any) -> list[int]:
        return [envelope.seq for envelope in await storage.read(SCOPE, **options)]

    assert await seqs(before_seq=3) == [1, 2]
    assert await seqs(after_seq=2, before_seq=5) == [3, 4]
    assert await seqs(before_seq=0) == []
    assert await seqs(before_seq=100) == [1, 2, 3, 4, 5, 6, 7]
    assert await seqs(threads={one.id}) == [1, 3, 5, 6], "the artifact event reaches everyone"
    assert await seqs(threads=[one.id, two.id], after_seq=4) == [5, 6, 7]
    assert await seqs(threads=()) == [5, 6]
    assert await seqs(limit=2, threads={two.id}, after_seq=2) == [4, 5]
    assert await seqs(limit=0) == []
    assert await seqs(last=2) == [6, 7], "the tail, oldest first"
    assert await seqs(last=2, threads={one.id}) == [5, 6]
    assert await seqs(last=10, after_seq=4) == [5, 6, 7]
    assert await seqs(last=0) == []
    tail = await seqs(last=2, threads={one.id})
    assert await seqs(last=2, threads={one.id}, before_seq=tail[0]) == [1, 3], "paging backwards"


async def test_envelopes_are_stamped_and_scoped(storage: Storage) -> None:
    await _create_thread(storage, "t1")
    [envelope] = await storage.read(SCOPE)
    assert (envelope.seq, envelope.workspace_id, envelope.thread_id, envelope.actor) == (
        1,
        "ws_1",
        "t1",
        ALICE,
    )
    assert envelope.ts.tzinfo is not None
    assert envelope.traceparent is None, "saved without a trace context"


async def test_envelopes_keep_the_trace_context_they_were_saved_with(storage: Storage) -> None:
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    command = CreateThread(thread_id="t1")
    async with storage.transaction(SCOPE) as tx:
        state = await tx.load(needs(command, actor=ALICE))
        [saved] = await tx.save(
            commit(command, state, actor=ALICE), actor=ALICE, traceparent=traceparent
        )
    assert saved.traceparent == traceparent
    assert await storage.read(SCOPE) == [saved]


async def test_leases_belong_to_their_holder(storage: Storage) -> None:
    ttl = timedelta(minutes=1)
    assert await storage.acquire_lease(SCOPE, "k", "a", ttl)
    assert await storage.acquire_lease(SCOPE, "k", "a", ttl), "the holder can renew"
    assert not await storage.acquire_lease(SCOPE, "k", "b", ttl)
    await storage.release_lease(SCOPE, "k", "b")  # not b's to release
    assert not await storage.acquire_lease(SCOPE, "k", "b", ttl)
    await storage.release_lease(SCOPE, "k", "a")
    assert await storage.acquire_lease(SCOPE, "k", "b", ttl)
    await storage.release_lease(SCOPE, "missing", "b")


async def test_an_expired_lease_can_be_taken(storage_factory: StorageFactory) -> None:
    now = datetime(2026, 9, 28, tzinfo=UTC)
    storage = storage_factory(lambda: now)
    assert await storage.acquire_lease(SCOPE, "k", "a", timedelta(seconds=30))
    now += timedelta(seconds=29)
    assert not await storage.acquire_lease(SCOPE, "k", "b", timedelta(seconds=30))
    now += timedelta(seconds=2)
    assert await storage.acquire_lease(SCOPE, "k", "b", timedelta(seconds=30))


async def test_a_transaction_saves_a_cursor_as_it_commits(storage: Storage) -> None:
    async with storage.transaction(SCOPE) as tx:
        await tx.save_cursor("consumed", 4)
        await tx.save_cursor("consumed", 2)
    assert await storage.cursor(SCOPE, "consumed") == 4

    async def fails() -> None:
        async with storage.transaction(SCOPE) as tx:
            await tx.save_cursor("consumed", 9)
            raise RuntimeError("rolled back")

    with pytest.raises(RuntimeError, match="rolled back"):
        await fails()
    assert await storage.cursor(SCOPE, "consumed") == 4, "not with a transaction that failed"
    async with storage.transaction(SCOPE) as tx:
        await tx.save_cursor("consumed", 3)
    assert await storage.cursor(SCOPE, "consumed") == 4, "only forward"


async def test_cursors_only_move_forward(storage: Storage) -> None:
    assert await storage.cursor(SCOPE, "mirror") == 0
    await storage.save_cursor(SCOPE, "mirror", 5)
    await storage.save_cursor(SCOPE, "mirror", 3)
    assert await storage.cursor(SCOPE, "mirror") == 5, "a lagging consumer cannot move it back"
    await storage.save_cursor(SCOPE, "mirror", 8)
    assert await storage.cursor(SCOPE, "mirror") == 8
    assert await storage.cursor(SCOPE, "another") == 0
    assert await storage.cursor(Scope("tenant_b", "ws_1"), "mirror") == 0, "per workspace"


async def test_concurrent_saves_of_a_cursor_leave_the_furthest(storage: Storage) -> None:
    await asyncio.gather(*(storage.save_cursor(SCOPE, "mirror", seq) for seq in (3, 4, 1, 2)))
    assert await storage.cursor(SCOPE, "mirror") == 4


async def test_a_handle_saves_its_workspaces_cursors(ws: Workspace, storage: Storage) -> None:
    await ws.save_cursor("mirror", 2)
    assert await ws.cursor("mirror") == 2
    assert await storage.cursor(SCOPE, "mirror") == 2


async def test_a_subscription_ends_when_its_storage_stream_ends() -> None:
    class FiniteStorage:
        async def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncGenerator[Envelope]:
            yield Envelope(
                seq=1,
                id="e1",
                ts=datetime.now(UTC),
                workspace_id="ws_1",
                thread_id="t1",
                actor=ALICE,
                event=MessagePosted(thread_id="t1", message_id="m1", content="hi"),
            )

    ws = await Workspaces(cast(Any, FiniteStorage())).open("t", "w", actor=ALICE)
    assert [e.seq async for e in ws.subscribe()] == [1]
    assert isinstance(ws, Workspace)
