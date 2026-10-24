"""Diagrams' revisions thinned a day after they were saved: one an actor every ten minutes, the
first, the current and pending proposals' bases kept (artifactr ADR-0094)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from artifactr.core import (
    Actor,
    AgentActor,
    CreateArtifact,
    EditArtifact,
    ProposeChange,
    Revision,
    UserActor,
)
from artifactr.excalidraw import (
    EXCALIDRAW,
    EXCALIDRAW_TYPES,
    Diagram,
    element_patch,
    excalidraw_checks,
    excalidraw_key_of,
    retention,
    thin_revisions,
)
from artifactr.excalidraw.retention import THIN_AFTER, THIN_EVERY, thinned
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import (
    InMemoryStorage,
    Scope,
    Storage,
    Workspace,
    Workspaces,
    integration_gate,
)
from tests.databases import SQL_BACKENDS, empty_database
from tests.excalidraw.scenes import data, element
from tests.ui.toggles import Toggles

ALICE = UserActor(id="alice")
BOB = UserActor(id="bob")
SCOPE = Scope("tenant_a", "ws_1")
START = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


class Clock:
    """The storage's time, which a test moves."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture(params=["memory", *SQL_BACKENDS])
async def storage(
    request: pytest.FixtureRequest, tmp_path: Path, clock: Clock
) -> AsyncIterator[Storage]:
    if request.param == "memory":
        yield InMemoryStorage(clock=clock)
        return
    async with empty_database(request.param, tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        yield SqlStorage(engine, clock=clock)


@pytest.fixture
def toggles() -> Toggles:
    return Toggles()


@pytest.fixture
def workspaces(storage: Storage, toggles: Toggles) -> Workspaces:
    return Workspaces(
        storage,
        types=EXCALIDRAW_TYPES,
        checks=excalidraw_checks(),
        gate=integration_gate(toggles, excalidraw_key_of),
    )


async def _moved(ws: Workspace, x: float) -> None:
    """An edit of the diagram, as its handle's actor: element `a` moved to `x`."""
    head = await ws.get(Diagram, "d1")
    a = head.data.elements["a"]
    moved = a.model_copy(update={"version": a.version + 1, "x": x})
    edit = element_patch(head.data, {**head.data.elements, "a": moved})
    await ws.commit(EditArtifact(artifact_id="d1", base_version=head.version, patch=edit))


async def test_old_revisions_are_thinned_to_one_an_actor_every_ten_minutes(
    workspaces: Workspaces, storage: Storage, clock: Clock
) -> None:
    alice = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    bob = alice.as_actor(BOB)
    await alice.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("a")))
    )  # 1: kept, as made
    agent = AgentActor(thread_id="t1", run_id="r1", name="assistant", on_behalf_of=ALICE)
    for minute, ws in [(1, alice), (2, alice), (3, alice), (4, bob), (5, bob), (12, alice)]:
        clock.now = START + timedelta(minutes=minute)
        await _moved(ws, float(minute))  # 2, 3, 4 alice; 5, 6 bob; 7 alice, ten minutes later
        if minute == 2:
            # An agent's proposal, still pending, made on version 3: its base is kept.
            head = await alice.get(Diagram, "d1")
            await alice.as_actor(agent).commit(
                ProposeChange(
                    change=EditArtifact(
                        artifact_id="d1",
                        base_version=3,
                        patch=element_patch(head.data, {"z": element("z")}),
                    )
                )
            )
            # A proposal to make another diagram bases no revision on this one.
            await alice.as_actor(agent).commit(
                ProposeChange(
                    change=CreateArtifact(
                        kind="excalidraw_diagram", artifact_id="d2", data=data(element("b"))
                    )
                )
            )
    clock.now = START + timedelta(minutes=20)
    await _moved(alice, 20.0)  # 8: the current version
    now = START + THIN_AFTER + timedelta(hours=1)
    assert await thin_revisions(storage, SCOPE, now=now) == 2
    kept = [revision.version for revision in await alice.revisions("d1")]
    # 2 goes (alice's 4 is her latest in those ten minutes, 3 a proposal's base); 5 goes for 6.
    assert kept == [1, 3, 4, 6, 7, 8]
    assert (await alice.get(Diagram, "d1")).version == 8
    assert await thin_revisions(storage, SCOPE, now=now) == 0, "thinned once is thinned"


async def test_revisions_a_day_old_or_less_are_kept(
    workspaces: Workspaces, storage: Storage, clock: Clock
) -> None:
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("a")))
    )
    for step in range(4):
        clock.now = START + timedelta(seconds=step)
        await _moved(ws, float(step))
    assert await thin_revisions(storage, SCOPE, now=START + THIN_AFTER - timedelta(minutes=1)) == 0
    assert await thin_revisions(storage, SCOPE, now=START + THIN_AFTER + timedelta(minutes=1)) == 2


async def test_nothing_is_thinned_where_diagrams_are_off(
    workspaces: Workspaces, storage: Storage, toggles: Toggles
) -> None:
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("a")))
    )
    for step in range(3):
        await _moved(ws, float(step))
    toggles.off["ws_1"] = {EXCALIDRAW}
    later = START + timedelta(days=30)
    assert await thin_revisions(storage, SCOPE, now=later, integrations=toggles) == 0
    toggles.off.clear()
    assert await thin_revisions(storage, SCOPE, now=later, integrations=toggles) == 1


def _revision(
    version: int, at: datetime | None, actor: Actor = ALICE, proposal_id: str | None = None
) -> Revision:
    return Revision(
        artifact_id="d1",
        version=version,
        kind="excalidraw_diagram",
        data={},
        actor=actor,
        at=at,
        proposal_id=proposal_id,
    )


def test_undated_revisions_count_as_old_and_one_an_actor_is_kept() -> None:
    revisions = [
        _revision(1, None),
        _revision(2, None),
        _revision(3, None, BOB),
        _revision(4, None),
        _revision(5, None, BOB),
        _revision(6, START),
    ]
    assert thinned(revisions, now=START + THIN_AFTER * 2) == [2, 3]


def test_a_short_history_and_the_span_bounds() -> None:
    assert thinned([_revision(1, None), _revision(2, None)], now=START) == []
    edge = START.replace(minute=0)
    revisions = [
        _revision(1, edge),
        _revision(2, edge + THIN_EVERY - timedelta(seconds=1)),
        _revision(3, edge + THIN_EVERY),  # the next ten minutes
        _revision(4, edge + THIN_EVERY + timedelta(seconds=1)),
        _revision(5, edge + THIN_EVERY * 3),
    ]
    assert thinned(revisions, now=edge + THIN_AFTER * 2) == [3]
    with pytest.raises(ValueError, match="time zone"):
        thinned(revisions, now=datetime(2026, 10, 1))


def test_an_accepted_proposals_revision_is_kept_and_one_exactly_a_day_old() -> None:
    revisions = [
        _revision(1, START),
        _revision(2, START, proposal_id="p1"),
        _revision(3, START),
        _revision(4, START),
        _revision(5, START + THIN_AFTER),
    ]
    # 2 an accepted proposal made; of 3 and 4, alice's latest in those ten minutes is 4.
    assert thinned(revisions, now=START + THIN_AFTER + timedelta(minutes=5)) == [3]
    edge = [_revision(1, START), _revision(2, START), _revision(3, START), _revision(4, START)]
    assert thinned(edge, now=START + THIN_AFTER) == [], "exactly a day old: kept"


async def test_versions_are_forgotten_a_few_at_a_time(
    workspaces: Workspaces, storage: Storage, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retention, "CHUNK", 1)
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("a")))
    )
    for step in range(4):
        await _moved(ws, float(step))
    assert await thin_revisions(storage, SCOPE, now=START + THIN_AFTER * 2) == 2
