"""A lease on an artifact (ADR-0071): one holder at a time, renewed by its holder, taken once it
expires, and advisory, over every storage."""

import asyncio
import itertools
from collections.abc import AsyncGenerator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, override

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from artifactr.core import NotFound, UserActor, ValidationFailed
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import (
    ArtifactBusy,
    ArtifactLease,
    InMemoryStorage,
    Scope,
    Storage,
    Workspace,
    Workspaces,
)
from tests.artifact_types import Note
from tests.databases import SQL_BACKENDS, empty_database
from tests.workspace.conftest import ALICE, StorageFactory

START = datetime(2026, 10, 17, 9, tzinfo=UTC)
HOUR = timedelta(hours=1)
BOB = UserActor(id="bob", name="Bob")


class Clock:
    """A clock the test moves."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


async def _workspace(storage: Storage, workspace_id: str = "w1") -> Workspace:
    ws = await Workspaces(storage).open("acme", workspace_id, actor=ALICE)
    await ws.create(Note(text="draft"), artifact_id="a1")
    return ws


@pytest.fixture
async def ws(storage_factory: StorageFactory, clock: Clock) -> Workspace:
    return await _workspace(storage_factory(clock))


async def test_a_lease_names_its_holder_and_expiry(ws: Workspace) -> None:
    assert await ws.artifact_lease("a1") is None
    lease = await ws.lease_artifact("a1", holder="checkout:c1:alice", ttl=8 * HOUR)
    assert lease == ArtifactLease("a1", "checkout:c1:alice", START + 8 * HOUR)
    assert await ws.as_actor(BOB).artifact_lease("a1") == lease, "viewers see who has it"


async def test_its_holder_renews_it(ws: Workspace, clock: Clock) -> None:
    await ws.lease_artifact("a1", holder="h", ttl=HOUR)
    clock.now += HOUR / 2
    renewed = await ws.lease_artifact("a1", holder="h", ttl=HOUR)
    assert renewed.expires_at == clock.now + HOUR


async def test_another_holder_is_refused_with_the_lease(ws: Workspace) -> None:
    held = await ws.lease_artifact("a1", holder="checkout:c1:alice", ttl=HOUR)
    with pytest.raises(ArtifactBusy) as refused:
        await ws.as_actor(BOB).lease_artifact("a1", holder="edit:e1", ttl=HOUR)
    assert refused.value.lease == held
    assert refused.value.code == "invalid_state"
    assert "checkout:c1:alice" in refused.value.message


async def test_another_holder_takes_it_once_it_expires(ws: Workspace, clock: Clock) -> None:
    await ws.lease_artifact("a1", holder="a", ttl=HOUR)
    clock.now += HOUR
    assert await ws.artifact_lease("a1") is None
    taken = await ws.lease_artifact("a1", holder="b", ttl=HOUR)
    assert taken.holder == "b"
    with pytest.raises(ArtifactBusy):
        await ws.lease_artifact("a1", holder="a", ttl=HOUR)


async def test_only_its_holder_releases_it(ws: Workspace) -> None:
    held = await ws.lease_artifact("a1", holder="a", ttl=HOUR)
    await ws.release_artifact("a1", holder="b")
    assert await ws.artifact_lease("a1") == held
    await ws.release_artifact("a1", holder="a")
    assert await ws.artifact_lease("a1") is None


async def test_the_lease_is_advisory(ws: Workspace) -> None:
    await ws.lease_artifact("a1", holder="checkout:c1:alice", ttl=HOUR)
    note = await ws.get(Note, "a1")
    await ws.as_actor(BOB).commit(note.edit_text("draft", "final"))
    assert (await ws.get(Note, "a1")).data.text == "final", "core doesn't know of it"


async def test_a_lease_is_on_an_artifact_that_exists(ws: Workspace) -> None:
    with pytest.raises(NotFound):
        await ws.lease_artifact("a_none", holder="h", ttl=HOUR)
    with pytest.raises(NotFound):
        await ws.artifact_lease("a_none")
    with pytest.raises(NotFound):
        await ws.release_artifact("a_none", holder="h")


@pytest.mark.parametrize("ttl", [timedelta(0), -HOUR])
async def test_a_lease_lasts_a_while(ws: Workspace, ttl: timedelta) -> None:
    with pytest.raises(ValidationFailed):
        await ws.lease_artifact("a1", holder="h", ttl=ttl)


class Meanwhile(InMemoryStorage):
    """Storage on which something happens to a lease between taking it and reading it."""

    def __init__(self, clock: Clock, then: Literal["ends", "is taken"]) -> None:
        super().__init__(clock=clock)
        self.clock = clock
        self.then = then

    @override
    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        acquired = await super().acquire_lease(scope, key, holder, ttl)
        if self.then == "ends":
            self.clock.now += 2 * HOUR
        else:
            self.clock.now += ttl
            assert await super().acquire_lease(scope, key, "someone else", HOUR)
        return acquired


async def test_a_lease_that_ends_before_it_is_read_refuses_with_none(clock: Clock) -> None:
    storage = Meanwhile(clock, "ends")
    ws = await _workspace(storage)
    assert await storage.acquire_lease(Scope("acme", "w1"), "artifact:a1", "a", HOUR)
    with pytest.raises(ArtifactBusy) as refused:
        await ws.lease_artifact("a1", holder="b", ttl=HOUR)
    assert refused.value.lease is None, "the agent may try again at once"
    assert "ended before it was read" in refused.value.message


async def test_a_lease_taken_from_its_holder_at_once_is_not_returned(clock: Clock) -> None:
    ws = await _workspace(Meanwhile(clock, "is taken"))
    with pytest.raises(ArtifactBusy) as refused:
        await ws.lease_artifact("a1", holder="a", ttl=timedelta(seconds=1))
    assert refused.value.lease is not None
    assert refused.value.lease.holder == "someone else"


# ─── the lease against a model of it, over every storage ─────────────────────


@dataclass(frozen=True)
class Take:
    holder: str
    seconds: int


@dataclass(frozen=True)
class Release:
    holder: str


@dataclass(frozen=True)
class Wait:
    seconds: int


type Step = Take | Release | Wait

HOLDERS = st.sampled_from(["checkout:c1:alice", "checkout:c2:alice", "edit:e1"])
STEPS: st.SearchStrategy[Step] = st.one_of(
    st.builds(Take, HOLDERS, st.integers(1, 120)),
    st.builds(Release, HOLDERS),
    st.builds(Wait, st.integers(0, 120)),
)
"""Taking or renewing a lease for some seconds, releasing it, and the clock moving on."""


@dataclass
class Shared:
    """One storage on one event loop for every example, each in a workspace of its own."""

    runner: asyncio.Runner
    storage: Storage
    clock: Clock
    workspaces: Iterator[str]


@asynccontextmanager
async def _storage_on(backend: str, directory: Path, clock: Clock) -> AsyncGenerator[Storage]:
    if backend == "memory":
        yield InMemoryStorage(clock=clock)
        return
    async with empty_database(backend, directory) as database:
        engine = database.engine()
        await create_schema(engine)
        yield SqlStorage(engine, clock=clock)


@pytest.fixture(params=["memory", *SQL_BACKENDS])
def shared(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Shared]:
    clock = Clock()
    with asyncio.Runner() as runner:
        stack = AsyncExitStack()
        storage = runner.run(stack.enter_async_context(_storage_on(request.param, tmp_path, clock)))
        try:
            yield Shared(runner, storage, clock, (f"w{n}" for n in itertools.count()))
        finally:
            runner.run(stack.aclose())


async def _agree(shared: Shared, steps: list[Step]) -> None:
    ws = await _workspace(shared.storage, next(shared.workspaces))
    clock = shared.clock
    held: tuple[str, datetime] | None = None  # the model: who holds it, until when
    for step in steps:
        live = held if held is not None and held[1] > clock.now else None
        match step:
            case Take(holder, seconds):
                if live is None or live[0] == holder:
                    lease = await ws.lease_artifact(
                        "a1", holder=holder, ttl=timedelta(seconds=seconds)
                    )
                    held = (holder, clock.now + timedelta(seconds=seconds))
                    assert (lease.holder, lease.expires_at) == held
                else:
                    with pytest.raises(ArtifactBusy) as refused:
                        await ws.lease_artifact("a1", holder=holder, ttl=timedelta(seconds=1))
                    assert refused.value.lease == ArtifactLease("a1", *live)
            case Release(holder):
                await ws.release_artifact("a1", holder=holder)
                if held is not None and held[0] == holder:
                    held = None
            case Wait(seconds):
                clock.now += timedelta(seconds=seconds)
        live = held if held is not None and held[1] > clock.now else None
        assert await ws.artifact_lease("a1") == (
            None if live is None else ArtifactLease("a1", *live)
        )


# 100 examples: 4.5 s alone on PostgreSQL, 72 s with every core busy beside xdist's other
# workers, past the minute a test may take (lattice ADR-0028). Five minutes.
@pytest.mark.timeout(300)
@settings(
    max_examples=100,
    deadline=None,
    # The storage is shared on purpose: each example works in a workspace of its own.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(steps=st.lists(STEPS, max_size=12))
def test_a_lease_has_one_holder_at_a_time(shared: Shared, steps: list[Step]) -> None:
    shared.runner.run(_agree(shared, steps))
