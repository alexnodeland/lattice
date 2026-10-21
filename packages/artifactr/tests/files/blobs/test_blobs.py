"""The blob store, on memory, SQLite and PostgreSQL, as the application's role and as the owner.

Bytes are named by their digest, computed as they arrive; a blob's access is its artifact's, in
its tenant's workspace; and collection keeps what is named, or was put lately.
"""

import asyncio
import hashlib
import itertools
from collections.abc import AsyncIterable, AsyncIterator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from artifactr.files.blobs import DEFAULT_LIMIT, MOST, Blobs, InMemoryBlobs, TooLarge, once
from artifactr.files.blobs.port import MIB, check_limit
from artifactr.files.manifest import DOCX, Blob
from artifactr.files.sql import SqlBlobs, create_schema
from artifactr.workspace import Scope
from tests.databases import SQL_BACKENDS, empty_database
from tests.files.clock import FakeClock
from tests.files.conftest import Stores

ACME = Scope("acme", "w1")
GLOBEX = Scope("globex", "w1")
DAY = timedelta(days=1)


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def blobs(stores: Stores) -> Blobs:
    return stores.blobs


async def test_bytes_are_named_by_their_digest_as_they_arrive(blobs: Blobs) -> None:
    put = await blobs.put(ACME, "a1", chunks(b"hello, ", b"world"), DOCX)
    assert put == Blob(sha256=sha256(b"hello, world"), size=12, media_type=DOCX)
    assert await blobs.get(ACME, "a1", put.sha256) == b"hello, world"
    empty = await blobs.put(ACME, "a1", chunks(), "text/plain")
    assert (empty.size, await blobs.get(ACME, "a1", empty.sha256)) == (0, b"")


async def test_a_blob_is_its_artifacts_in_its_tenants_workspace(blobs: Blobs) -> None:
    put = await blobs.put(ACME, "a1", once(b"contract"), DOCX)
    assert await blobs.get(ACME, "a1", put.sha256) == b"contract"
    assert await blobs.get(ACME, "a2", put.sha256) is None, "another artifact names it in vain"
    assert await blobs.get(Scope("acme", "w2"), "a1", put.sha256) is None
    assert await blobs.get(GLOBEX, "a1", put.sha256) is None, "nothing across tenants"
    assert await blobs.get(ACME, "a1", sha256(b"other")) is None


async def test_putting_the_same_bytes_again_stores_nothing_new(blobs: Blobs) -> None:
    first = await blobs.put(ACME, "a1", once(b"same"), DOCX)
    again = await blobs.put(ACME, "a1", once(b"same"), DOCX)
    assert first == again
    other = await blobs.put(GLOBEX, "a1", once(b"same"), DOCX)
    assert other.sha256 == first.sha256, "the same bytes, kept apart"
    assert await blobs.collect(ACME, set(), before=FakeClock().now + DAY) == 1, "one blob"


async def test_two_tenants_read_and_collect_nothing_of_each_other(
    blobs: Blobs, clock: FakeClock
) -> None:
    acme = await blobs.put(ACME, "a1", once(b"acme's"), DOCX)
    globex = await blobs.put(GLOBEX, "a1", once(b"globex's"), DOCX)
    assert await blobs.get(GLOBEX, "a1", acme.sha256) is None
    assert await blobs.get(ACME, "a1", globex.sha256) is None
    assert await blobs.collect(GLOBEX, set(), before=clock.now + DAY) == 1
    assert await blobs.get(ACME, "a1", acme.sha256) == b"acme's", "only globex's was collected"


async def test_bytes_larger_than_the_limit_are_refused_as_they_arrive(stores: Stores) -> None:
    async def endless() -> AsyncIterable[bytes]:
        while True:
            yield b"\0" * MIB

    with pytest.raises(TooLarge) as refused:
        await stores.blobs.put(ACME, "a1", endless(), DOCX)
    assert refused.value.limit == DEFAULT_LIMIT
    assert str(DEFAULT_LIMIT) in str(refused.value)


@pytest.mark.parametrize("limit", [0, MOST + 1])
def test_a_limit_is_from_a_byte_to_100_mib(limit: int) -> None:
    assert check_limit(MOST) == MOST
    with pytest.raises(ValueError, match="between 1 and"):
        InMemoryBlobs(limit=limit)


async def test_a_store_keeps_to_its_own_limit(tmp_path: Path) -> None:
    small = InMemoryBlobs(limit=4)
    await small.put(ACME, "a1", once(b"four"), DOCX)
    with pytest.raises(TooLarge):
        await small.put(ACME, "a1", chunks(b"fo", b"ur", b"!"), DOCX)
    async with empty_database("sqlite", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        with pytest.raises(TooLarge):
            await SqlBlobs(engine, limit=4).put(ACME, "a1", once(b"five!"), DOCX)


async def test_collection_keeps_what_is_named_or_put_lately(blobs: Blobs, clock: FakeClock) -> None:
    named = await blobs.put(ACME, "a1", once(b"named"), DOCX)
    orphan = await blobs.put(ACME, "a1", once(b"orphan"), DOCX)
    put_again = await blobs.put(ACME, "a1", once(b"put again"), DOCX)
    elsewhere = await blobs.put(ACME, "a2", once(b"named"), DOCX)
    clock.advance(2 * DAY)
    await blobs.put(ACME, "a1", once(b"put again"), DOCX)  # for a commit about to be made
    fresh = await blobs.put(ACME, "a1", once(b"fresh"), DOCX)
    referenced = {("a1", named.sha256)}
    assert await blobs.collect(ACME, referenced, before=clock.now - DAY) == 2
    for kept in (named, put_again, fresh):
        assert await blobs.get(ACME, "a1", kept.sha256) is not None
    assert await blobs.get(ACME, "a1", orphan.sha256) is None
    assert await blobs.get(ACME, "a2", elsewhere.sha256) is None, "named for a1 only"
    assert await blobs.collect(ACME, referenced, before=clock.now - DAY) == 0


async def test_collection_deletes_in_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three batches and a part of one: of five, so a dozen blobs take them, not 1,201."""
    monkeypatch.setattr("artifactr.files.sql.blobs.BATCH", 5)
    clock = FakeClock()
    async with empty_database("sqlite", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        blobs = SqlBlobs(engine, clock=clock)
        for n in range(16):
            await blobs.put(ACME, "a1", once(str(n).encode()), DOCX)
        assert await blobs.collect(ACME, set(), before=clock.now + DAY) == 16


# ─── collection against a model of it, over every storage ────────────────────


@dataclass(frozen=True)
class Put:
    artifact: str
    data: bytes
    days_ago: int


PUTS = st.lists(
    st.builds(Put, st.sampled_from(["a1", "a2"]), st.binary(max_size=3), st.integers(0, 3)),
    max_size=10,
)


@dataclass
class Shared:
    """One store on one event loop for every example, each in a workspace of its own."""

    runner: asyncio.Runner
    blobs: Blobs
    clock: FakeClock
    workspaces: Iterator[Scope]


@asynccontextmanager
async def _blobs_on(backend: str, directory: Path, clock: FakeClock) -> AsyncIterator[Blobs]:
    if backend == "memory":
        yield InMemoryBlobs(clock=clock)
        return
    async with empty_database(backend, directory) as database:
        engine = database.engine()
        await create_schema(engine)
        yield SqlBlobs(engine, clock=clock)


@pytest.fixture(params=["memory", *SQL_BACKENDS])
def shared(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Shared]:
    clock = FakeClock()
    with asyncio.Runner() as runner:
        stack = AsyncExitStack()
        blobs = runner.run(stack.enter_async_context(_blobs_on(request.param, tmp_path, clock)))
        try:
            yield Shared(runner, blobs, clock, (Scope("acme", f"w{n}") for n in itertools.count()))
        finally:
            runner.run(stack.aclose())


async def _collect(shared: Shared, puts: list[Put], named: list[int]) -> None:
    scope, start = next(shared.workspaces), shared.clock.now
    last_put: dict[tuple[str, str], int] = {}
    for put in sorted(puts, key=lambda p: -p.days_ago):  # oldest first, as time passes
        shared.clock.now = start - put.days_ago * DAY
        blob = await shared.blobs.put(scope, put.artifact, once(put.data), DOCX)
        last_put[(put.artifact, blob.sha256)] = put.days_ago
    keys = sorted(last_put)
    referenced = {keys[i % len(keys)] for i in named} if keys else set()
    shared.clock.now = start
    doomed = {key for key, days in last_put.items() if days > 1 and key not in referenced}
    assert await shared.blobs.collect(scope, referenced, before=start - DAY) == len(doomed)
    for artifact, digest in keys:
        found = await shared.blobs.get(scope, artifact, digest)
        assert (found is None) == ((artifact, digest) in doomed)


# 100 examples: 2.3 s alone on PostgreSQL, 53 s with every core busy beside xdist's other
# workers, near the minute a test may take: five minutes. A Hypothesis test keeps the thread
# method: Hypothesis replays a failure, and a signal's timer is spent by then (lattice ADR-0028).
@pytest.mark.timeout(300, method="thread")
@settings(
    max_examples=100,
    deadline=None,
    # The store is shared on purpose: each example works in a workspace of its own.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(puts=PUTS, named=st.lists(st.integers(0, 20), max_size=4))
def test_collection_deletes_exactly_what_is_old_and_unnamed(
    shared: Shared, puts: list[Put], named: list[int]
) -> None:
    shared.runner.run(_collect(shared, puts, named))
