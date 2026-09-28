"""The storage contract, below the workspace: transactions, reads and leases."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from artifactr.core import (
    CreateThread,
    Envelope,
    MessagePosted,
    Needs,
    State,
    UserActor,
    commit,
    needs,
)
from artifactr.workspace import InMemoryStorage, Scope, Storage, Workspace, Workspaces

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


async def test_a_transaction_that_raises_rolls_back(storage: Storage) -> None:
    async def save_then_fail() -> None:
        async with storage.transaction(SCOPE) as tx:
            await tx.save(
                commit(CreateThread(thread_id="t1"), State(threads={"t1": None}), actor=ALICE),
                actor=ALICE,
            )
            await tx.append_history("t1", b"[]")
            raise RuntimeError("the host failed after saving")

    with pytest.raises(RuntimeError):
        await save_then_fail()
    assert await storage.head_seq(SCOPE) == 0
    assert await storage.thread(SCOPE, "t1") is None
    assert await storage.history(SCOPE, "t1") == []


async def test_reads_filter_and_page(storage: Storage) -> None:
    for thread_id in ("t1", "t2", "t3"):
        await _create_thread(storage, thread_id)
    assert [e.seq for e in await storage.read(SCOPE, after_seq=1, limit=1)] == [2]
    assert await storage.artifacts(SCOPE, kind="note") == []


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


async def test_an_expired_lease_can_be_taken() -> None:
    now = datetime(2026, 9, 28, tzinfo=UTC)
    storage = InMemoryStorage(clock=lambda: now)
    assert await storage.acquire_lease(SCOPE, "k", "a", timedelta(seconds=30))
    now += timedelta(seconds=31)
    assert await storage.acquire_lease(SCOPE, "k", "b", timedelta(seconds=30))


async def test_a_subscription_ends_when_its_storage_stream_ends() -> None:
    class FiniteStorage:
        async def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncIterator[Envelope]:
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
