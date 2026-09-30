"""A caller of SQL storage cancelled anywhere leaves no lock or connection behind.

A cancellation lands wherever its task is: a stopped run, a WebSocket that disconnects, a
claim's renewal when the claim ends, a timeout, or an anyio cancel scope, which cancels its task
again until the task ends. SQLAlchemy takes a statement cancelled part-way for a lost connection,
so SQL storage awaits every database call to its end and raises the cancellation after it.

The cancellations are seeded, not deterministic: where one lands depends on the database's timing.
"""

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest
from sqlalchemy.pool import QueuePool

from artifactr.core import Envelope, UserActor
from artifactr.sql import SqlStorage
from artifactr.sql.storage import _to_the_end
from artifactr.workspace import Scope, Workspaces
from tests.databases import Database

ALICE = UserActor(id="alice")
SCOPE = Scope("tenant_a", "ws_1")
ITERATIONS = 100
MINUTE = timedelta(minutes=1)
LOCK_TIMEOUT = timedelta(milliseconds=250)
"""How long the other process waits for a lock, so one left behind fails the test, not hangs it."""

type Operation = Callable[[], Awaitable[object]]
type Cancel = Callable[[Operation, random.Random], Awaitable[None]]


@pytest.mark.parametrize("ending", ["returns", "raises", "is cancelled"])
async def test_a_cancelled_call_ends_before_the_cancellation_is_raised(ending: str) -> None:
    release = asyncio.Event()
    ended: list[str] = []

    async def call() -> None:
        await release.wait()
        ended.append(ending)
        if ending == "raises":
            raise RuntimeError("the statement failed")
        if ending == "is cancelled":
            raise asyncio.CancelledError

    caller = asyncio.create_task(_to_the_end(call()))
    for _ in range(3):  # cancelled again at every await, as anyio does
        await asyncio.sleep(0)
        caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done(), "the call is still running"
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert ended == [ending]


async def cancel_after_some_yields(operation: Operation, rng: random.Random) -> None:
    task = asyncio.ensure_future(operation())
    for _ in range(rng.randrange(40)):
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    if not task.cancelled():
        task.result()


async def cancel_until_it_ends(operation: Operation, rng: random.Random) -> None:
    task = asyncio.ensure_future(operation())
    for _ in range(rng.randrange(40)):
        await asyncio.sleep(0)
    while not task.done():
        task.cancel()
        # Not at every turn of the loop, as anyio does: that starves aiosqlite's thread of the
        # GIL on Linux, and a call takes seconds to end.
        await asyncio.sleep(0.001)
    if not task.cancelled():
        task.result()


async def time_out(operation: Operation, rng: random.Random) -> None:
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(rng.random() / 200):  # up to 5 ms
            await operation()


CANCELS: dict[str, Cancel] = {
    "after some yields": cancel_after_some_yields,
    "until it ends": cancel_until_it_ends,
    "by a timeout": time_out,
}


@pytest.mark.parametrize("cancel", CANCELS)
@pytest.mark.parametrize("operation", ["commit", "read", "acquire_lease", "subscribe"])
async def test_a_cancelled_call_leaves_the_workspace_usable(
    schema: Database, operation: str, cancel: str
) -> None:
    here = schema.engine()
    pool = here.pool
    assert isinstance(pool, QueuePool)
    storage = SqlStorage(here)
    workspace = await Workspaces(storage).open(SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE)
    # Another process, which gives up waiting for a lock rather than waiting on one never freed.
    elsewhere = await Workspaces(SqlStorage(schema.engine(lock_timeout=LOCK_TIMEOUT))).open(
        SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE
    )
    await workspace.create_thread()  # so a subscription has a page to read

    async def first_page() -> Envelope:
        async with contextlib.aclosing(storage.subscribe(SCOPE)) as envelopes:
            return await anext(envelopes)

    operations: dict[str, Operation] = {
        "commit": workspace.create_thread,
        "read": lambda: storage.read(SCOPE),
        "acquire_lease": lambda: storage.acquire_lease(SCOPE, "thread:t1", "here", MINUTE),
        "subscribe": first_page,
    }
    rng = random.Random(f"{operation} {cancel}")
    for iteration in range(ITERATIONS):
        await CANCELS[cancel](operations[operation], rng)
        assert pool.checkedout() == 0, f"iteration {iteration} kept its connection"
        await elsewhere.create_thread()
        await workspace.create_thread()
    log = await storage.read(SCOPE)
    assert [envelope.seq for envelope in log] == list(range(1, len(log) + 1))
