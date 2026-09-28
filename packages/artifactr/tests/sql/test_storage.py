"""SQL storage across connections and processes: locking, polling, leases and stored JSON."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from artifactr.core import (
    Applied,
    CreateThread,
    Needs,
    State,
    Thread,
    UserActor,
    VersionConflict,
    commit,
)
from artifactr.sql import SqlStorage, create_schema, migrate
from artifactr.workspace import Scope, Workspace, Workspaces
from tests.artifact_types import Checklist, Item, Note

ALICE = UserActor(id="alice")
SCOPE = Scope("tenant_a", "ws_1")


async def _open(storage: SqlStorage) -> Workspace:
    return await Workspaces(storage).open(SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE)


@pytest.fixture
async def schema(engine: AsyncEngine) -> AsyncEngine:
    await create_schema(engine)
    return engine


async def test_a_migrated_database_stores_workspaces(engine: AsyncEngine) -> None:
    await migrate(engine)
    ws = await _open(SqlStorage(engine))
    thread = await ws.create_thread("Launch")
    assert await ws.threads() == [thread]


@pytest.mark.parametrize("workspace", ["new", "existing"])
async def test_a_transaction_waits_for_the_one_before_it(
    schema: AsyncEngine, workspace: str
) -> None:
    first, second = SqlStorage(schema), SqlStorage(schema)
    if workspace == "existing":
        await (await _open(first)).create_thread()
    began, release = asyncio.Event(), asyncio.Event()

    async def save_when_released() -> None:
        async with first.transaction(SCOPE) as tx:
            began.set()
            await release.wait()
            create = CreateThread(thread_id="t1")
            await tx.save(commit(create, State(threads={"t1": None}), actor=ALICE), actor=ALICE)

    async def load() -> Thread | None:
        async with second.transaction(SCOPE) as tx:
            return (await tx.load(Needs(threads=frozenset({"t1"})))).threads["t1"]

    saver = asyncio.create_task(save_when_released())
    await began.wait()
    loader = asyncio.create_task(load())
    await asyncio.sleep(0.2)
    assert not loader.done(), "the second transaction waits for the first to end"
    release.set()
    await saver
    assert await asyncio.wait_for(loader, timeout=5) is not None, "and then sees its changes"


async def test_concurrent_commits_get_gap_free_seqs(schema: AsyncEngine) -> None:
    handles = [await _open(SqlStorage(schema)) for _ in range(4)]
    await asyncio.gather(*(ws.create_thread(f"thread {i}") for i, ws in enumerate(handles * 3)))
    assert [e.seq for e in await handles[0].read()] == list(range(1, 13))
    assert await handles[0].head_seq() == 12
    assert len(await handles[0].threads()) == 12


async def test_concurrent_edits_of_one_version_conflict(schema: AsyncEngine) -> None:
    ws = await _open(SqlStorage(schema))
    await ws.create(Note(text="draft"), artifact_id="n1")
    note = await ws.get(Note, "n1")
    others = [await _open(SqlStorage(schema)) for _ in range(5)]
    outcomes = await asyncio.gather(
        *(other.commit(note.edit_text("draft", f"edit {i}")) for i, other in enumerate(others)),
        return_exceptions=True,
    )
    assert sum(isinstance(outcome, Applied) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, VersionConflict) for outcome in outcomes) == 4
    assert [r.version for r in await ws.revisions("n1")] == [1, 2]


async def test_subscriptions_poll_for_commits_made_elsewhere(schema: AsyncEngine) -> None:
    here = await _open(SqlStorage(schema, poll_interval=timedelta(milliseconds=20)))
    elsewhere = await _open(SqlStorage(schema))  # as if in another process
    received: list[int] = []

    async def follow() -> None:
        async for envelope in here.subscribe():
            received.append(envelope.seq)
            if len(received) == 2:
                return

    follower = asyncio.create_task(follow())
    await asyncio.sleep(0.05)  # the follower has read the empty log and is waiting
    await elsewhere.create_thread()
    await elsewhere.create_thread()
    await asyncio.wait_for(follower, timeout=5)
    assert received == [1, 2]


async def test_one_of_many_concurrent_holders_gets_a_lease(schema: AsyncEngine) -> None:
    storages = [SqlStorage(schema) for _ in range(8)]
    taken = await asyncio.gather(
        *(
            storage.acquire_lease(SCOPE, "k", f"holder {i}", timedelta(minutes=1))
            for i, storage in enumerate(storages)
        )
    )
    assert sorted(taken) == [False] * 7 + [True]


async def test_leases_belong_to_their_workspace(schema: AsyncEngine) -> None:
    storage = SqlStorage(schema)
    ttl = timedelta(minutes=1)
    assert await storage.acquire_lease(SCOPE, "k", "a", ttl)
    assert await storage.acquire_lease(Scope("tenant_b", "ws_1"), "k", "b", ttl)
    assert await storage.acquire_lease(Scope("tenant_a", "ws_2"), "k", "b", ttl)


async def test_lease_expiry_compares_instants_whatever_the_clocks_zone(
    schema: AsyncEngine,
) -> None:
    now = datetime(2026, 9, 28, 12, tzinfo=UTC)
    storage = SqlStorage(schema, clock=lambda: now)
    assert await storage.acquire_lease(SCOPE, "k", "a", timedelta(seconds=30))
    now = (now + timedelta(seconds=29)).astimezone(timezone(timedelta(hours=-7)))
    assert not await storage.acquire_lease(SCOPE, "k", "b", timedelta(seconds=30))
    now = (now + timedelta(seconds=2)).astimezone(timezone(timedelta(hours=5)))
    assert await storage.acquire_lease(SCOPE, "k", "b", timedelta(seconds=30))


async def test_stored_data_keeps_its_key_order(schema: AsyncEngine) -> None:
    ws = await _open(SqlStorage(schema))
    items = {"zeta": Item(title="Z"), "b": Item(title="B"), "alpha_long": Item(title="A")}
    await ws.create(Checklist(items=items), artifact_id="c1")
    stored = await ws.get(Checklist, "c1")
    assert list(stored.data.items) == ["zeta", "b", "alpha_long"]
