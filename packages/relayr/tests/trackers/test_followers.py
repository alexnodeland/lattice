"""Reading back (lattice RFC-0004): what a follower publishes of a fake tracker, on every ledger.

Each test polls by hand, as the follower does each interval, so the clock and the tracker are
the test's. Phase 2's exit criteria are named where they are tested.
"""

from datetime import timedelta

import pytest

import reflexr
from reflexr.core import NotFound, Tick
from reflexr.workspace import RunFailure
from relayr.ledger import Ledger, TrackerDeadLetter, WorkspaceKey
from relayr.outbound.ids import canonical
from relayr.trackers import (
    LOOK_BACK,
    LOOP_CAP,
    FakeTracker,
    ItemFields,
    TrackerBinding,
    Unauthorized,
    Unavailable,
    event_id,
)
from relayr.trackers.events import (
    SOURCE,
    ItemChanged,
    ItemCommented,
    ItemCreated,
    ItemRemoved,
    TrackerEvent,
)
from tests.clock import START, FakeClock
from tests.trackers.conftest import BINDING, KEY, PROJECT, TENANT
from tests.trackers.following import Following, Odd, changes, following

SECOND = timedelta(seconds=1)


@pytest.fixture
def app(ledger: Ledger, clock: FakeClock) -> Following:
    return following(ledger, clock)


async def seeded(app: Following) -> None:
    """The binding's first read: it publishes nothing."""
    assert await app.poll()
    assert await app.events() == []
    app.clock.advance(SECOND)


# ─── what is published ────────────────────────────────────────────────────────


async def test_a_new_binding_over_existing_items_publishes_nothing(app: Following) -> None:
    first = app.tracker.add(PROJECT, "Before")
    app.tracker.reply(first, "<p>Old.</p>")
    app.tracker.add(PROJECT, "Also before")
    await seeded(app)
    assert await app.poll()
    assert await app.events() == [], "nothing changed since"
    app.tracker.edit(first, ItemFields(title="After"))
    assert await app.poll()
    assert changes(await app.events()) == [("changed", first.id, "title", "After")]


async def test_a_binding_since_a_time_publishes_what_changed_since_as_created(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock, bindings={KEY: BINDING.model_copy(update={"since": START})})
    clock.advance(-SECOND)
    app.tracker.add(PROJECT, "Before")
    clock.advance(SECOND * 2)
    after = app.tracker.add(PROJECT, "After")
    assert await app.poll()
    assert changes(await app.events()) == [("created", after.id, "After")]


async def test_what_a_person_does_is_published_once(app: Following) -> None:
    await seeded(app)
    item = app.tracker.add(PROJECT, "Filed by hand", by="ada")
    assert await app.poll()
    app.clock.advance(SECOND)
    app.tracker.edit(item, ItemFields(state="started", labels=("bug",)), by="ada")
    app.tracker.reply(item, "<p>On it.</p>", by="ada")
    assert await app.poll()
    assert await app.poll(), "a page read again publishes nothing new"
    events = await app.events()
    assert changes(events) == [
        ("created", item.id, "Filed by hand"),
        ("changed", item.id, "state", "started"),
        ("changed", item.id, "labels", ["bug"]),
        ("commented", item.id, "<p>On it.</p>"),
    ]
    created, state, _, commented = events
    assert isinstance(created, ItemCreated)
    assert (created.tracker, created.project, created.name, created.actor) == (
        "fake",
        PROJECT,
        "OPS-1",
        "ada",
    )
    assert created.link == "https://tracker.test/ops/1"
    assert isinstance(state, ItemChanged)
    assert (state.old, state.new, state.actor, state.key) == ("backlog", "started", "ada", None)
    assert isinstance(commented, ItemCommented)
    assert commented.author == "ada"
    envelopes = await app.published()
    assert all(e.actor == SOURCE for e in envelopes)
    assert all(e.id.startswith("trk_") for e in envelopes)


async def test_two_changes_between_polls_are_one_and_one_undone_is_none(app: Following) -> None:
    item = app.tracker.add(PROJECT, "Filed")
    await seeded(app)
    app.tracker.edit(item, ItemFields(priority="low"))
    app.tracker.edit(item, ItemFields(priority="high"))
    app.tracker.edit(item, ItemFields(title="Renamed"))
    app.tracker.edit(item, ItemFields(title="Filed"))
    assert await app.poll()
    assert changes(await app.events()) == [("changed", item.id, "priority", "high")]


async def test_ids_are_derived_from_what_an_event_says(app: Following) -> None:
    item = app.tracker.add(PROJECT, "Filed")
    await seeded(app)
    app.tracker.edit(item, ItemFields(title="Renamed"))
    assert await app.poll()
    [envelope] = await app.published()
    updated = app.tracker.items_in(PROJECT)[0].updated_at.isoformat()
    parts = (TENANT, KEY.workspace_id, PROJECT, "fake", item.id, "title")
    assert envelope.id == event_id(*parts, canonical("Renamed"), updated)


async def test_a_lost_snapshot_row_publishes_nothing_twice(app: Following) -> None:
    item = app.tracker.add(PROJECT, "Filed")
    await seeded(app)
    app.tracker.edit(item, ItemFields(title="Renamed"))
    assert await app.poll()
    await app.ledger.forget_snapshots(KEY)
    app.clock.advance(timedelta(days=1))
    assert await app.poll()
    assert changes(await app.events()) == [
        ("changed", item.id, "title", "Renamed"),
        ("created", item.id, "Renamed"),
    ], "a lost row's item is new again, once"
    assert await app.poll()
    assert len(await app.events()) == 2


# ─── reading back in time ─────────────────────────────────────────────────────


async def test_a_change_committed_older_than_the_cursor_is_published_once(
    app: Following,
) -> None:
    late, early = app.tracker.add(PROJECT, "Late"), app.tracker.add(PROJECT, "Early")
    await seeded(app)
    app.clock.advance(-SECOND * 30)  # committed now, with an older updated_at
    app.tracker.edit(late, ItemFields(title="Late, renamed"))
    app.clock.advance(SECOND * 60)
    app.tracker.edit(early, ItemFields(title="Early, renamed"))
    assert await app.poll()
    app.clock.advance(-SECOND * 90)
    app.tracker.edit(late, ItemFields(state="done"))  # older than the cursor, within the look-back
    app.clock.advance(SECOND * 90)
    assert await app.poll()
    assert await app.poll()
    assert sorted(changes(await app.events())) == sorted(
        [
            ("changed", late.id, "title", "Late, renamed"),
            ("changed", early.id, "title", "Early, renamed"),
            ("changed", late.id, "state", "done"),
        ]
    )


async def test_a_change_older_than_the_look_back_waits_for_the_sweep(app: Following) -> None:
    item = app.tracker.add(PROJECT, "Filed")
    other = app.tracker.add(PROJECT, "Other")
    await seeded(app)
    app.clock.advance(LOOK_BACK * 2)
    app.tracker.edit(other, ItemFields(title="Moved on"))
    assert await app.poll()
    app.clock.advance(-LOOK_BACK * 2)
    app.tracker.edit(item, ItemFields(title="Long ago"))
    app.clock.advance(LOOK_BACK * 2)
    assert await app.poll()
    assert changes(await app.events()) == [("changed", other.id, "title", "Moved on")]
    app.clock.advance(timedelta(days=1))
    assert await app.poll()
    assert changes(await app.events())[-1] == ("changed", item.id, "title", "Long ago")


async def test_a_follower_stopped_for_six_hours_loses_nothing_and_repeats_nothing(
    ledger: Ledger, clock: FakeClock
) -> None:
    """Phase 2: a relayr stopped for six hours (Plane's webhook deactivated) loses no change and
    publishes none twice."""
    first = following(ledger, clock)
    item = first.tracker.add(PROJECT, "Filed")
    await seeded(first)
    first.tracker.edit(item, ItemFields(title="Before the stop"))
    assert await first.poll()
    await first.followers.aclose()
    for hour in range(6):
        clock.advance(timedelta(hours=1))
        first.tracker.edit(item, ItemFields(priority=("low", "high")[hour % 2]))
        first.tracker.reply(item, f"<p>Hour {hour}.</p>")
        first.tracker.add(PROJECT, f"Filed at hour {hour}")
    clock.advance(timedelta(hours=1))
    again = following(ledger, clock, tracker=first.tracker, storage=first.storage)
    assert await again.poll()
    assert await again.poll()
    found = changes(await again.events())
    assert found[0] == ("changed", item.id, "title", "Before the stop")
    assert ("changed", item.id, "priority", "high") in found
    assert [c for c in found if c[0] == "commented"] == [
        ("commented", item.id, f"<p>Hour {hour}.</p>") for hour in range(6)
    ]
    assert len([c for c in found if c[0] == "created"]) == 6
    assert len(found) == len(set(map(repr, found))), "nothing published twice"


# ─── removals ─────────────────────────────────────────────────────────────────


async def test_the_sweep_publishes_what_left_the_list(app: Following) -> None:
    theirs = app.tracker.add(PROJECT, "Theirs")
    ours = await app.filed("dead-letter/a")
    archived = await app.filed("dead-letter/b")
    await seeded(app)
    app.tracker.delete(theirs)
    app.tracker.delete(ours)
    app.tracker.archive(archived)
    assert await app.poll()
    assert await app.events() == [], "a poll doesn't see what left"
    app.clock.advance(timedelta(days=1))
    assert await app.poll()
    assert sorted(changes(await app.events())) == sorted(
        [
            ("removed", theirs.id, None),
            ("removed", ours.id, True),
            ("removed", archived.id, False),
        ]
    )
    deleted = await app.ledger.tracked(KEY, "item", "dead-letter/a")
    assert deleted is not None
    assert deleted.deleted, "a deleted item files nothing again"
    kept = await app.ledger.tracked(KEY, "item", "dead-letter/b")
    assert kept is not None
    assert not kept.deleted, "an archived item is still filed"
    assert sorted(await app.ledger.snapshots(KEY)) == []
    app.clock.advance(timedelta(days=1))
    assert await app.poll()
    assert len(await app.events()) == 3


async def test_removals_the_budget_has_no_request_for_wait_for_the_next_sweep(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock, budget=2)
    first, second = await app.filed("dead-letter/a"), await app.filed("dead-letter/b")
    clock.advance(timedelta(minutes=1))
    await seeded(app)
    app.tracker.delete(first)
    app.tracker.delete(second)
    clock.advance(timedelta(days=1))
    assert await app.poll()  # the list, and one lookup
    assert changes(await app.events()) == [("removed", first.id, True)]
    clock.advance(timedelta(minutes=1))
    assert await app.poll()  # still sweeping
    assert changes(await app.events())[1:] == [("removed", second.id, True)]


async def test_another_project_bound_starts_over(ledger: Ledger, clock: FakeClock) -> None:
    app = following(ledger, clock)
    app.tracker.add(PROJECT, "Ops")
    await seeded(app)
    app.tracker.add("dev", "Dev")
    moved = following(
        ledger,
        clock,
        tracker=app.tracker,
        bindings={KEY: TrackerBinding(project="dev")},
        storage=app.storage,
    )
    assert await moved.poll()
    assert await moved.events() == [], "the new project is seeded, the old one forgotten"
    assert [s.item["title"] for s in (await ledger.snapshots(KEY)).values()] == ["Dev"]


# ─── echoes, chains and loops ─────────────────────────────────────────────────


async def test_relayrs_own_writes_are_not_published(app: Following) -> None:
    await seeded(app)
    item = await app.filed("dead-letter/a")
    assert await app.poll()
    app.clock.advance(SECOND)
    acting = await app.acting()
    await acting.set_state(item, "done")
    await acting.comment(item, "<p>Retried.</p>")
    await acting.update(item, ItemFields(labels=("lattice", "triaged")))
    assert await app.poll()
    assert await app.events() == []


async def test_a_person_restoring_a_value_relayr_wrote_is_published(app: Following) -> None:
    await seeded(app)
    item = await app.filed("dead-letter/a")
    await (await app.acting()).set_state(item, "done")
    assert await app.poll()
    app.clock.advance(SECOND)
    app.tracker.edit(item, ItemFields(state="todo"), by="ada")
    assert await app.poll()
    app.clock.advance(SECOND)
    app.tracker.edit(item, ItemFields(state="done"), by="ada")
    assert await app.poll()
    assert changes(await app.events()) == [
        ("changed", item.id, "state", "todo"),
        ("changed", item.id, "state", "done"),
    ], "an echo is dropped once"


async def test_a_persons_change_with_relayrs_names_no_actor(app: Following) -> None:
    await seeded(app)
    item = await app.filed("dead-letter/a")
    assert await app.poll()
    app.clock.advance(SECOND)
    app.tracker.edit(item, ItemFields(title="Renamed"), by="ada")
    await (await app.acting()).set_state(item, "done")
    assert await app.poll()
    [renamed] = await app.events()
    assert isinstance(renamed, ItemChanged)
    assert (renamed.field, renamed.actor, renamed.key) == ("title", None, "dead-letter/a")


async def test_a_persons_edit_of_a_filed_item_joins_its_chain_without_depth(
    ledger: Ledger, clock: FakeClock
) -> None:
    """Phase 2: a person's edit on Vikunja, of an item a run filed at the depth limit, is
    published and joins its chain."""
    app = following(ledger, clock, max_depth=1)
    await seeded(app)
    acting = await app.acting()
    item = await app.filed("dead-letter/a")
    assert await app.poll()
    app.clock.advance(SECOND)
    app.tracker.edit(item, ItemFields(description="<p>Fixed.</p>"), by=None)  # as Vikunja's
    app.tracker.reply(item, "<p>Done.</p>", by=None)
    assert await app.poll()
    envelopes = await app.published()
    *_, changed, commented = envelopes
    tracked = await ledger.tracked(KEY, "item", "dead-letter/a")
    assert tracked is not None
    assert {changed.correlation_id, commented.correlation_id} == {tracked.correlation_id}
    assert (changed.depth, changed.causation) == (0, None)
    assert isinstance(changed.event, ItemChanged)
    assert changed.event.actor is None
    assert acting.__class__.__name__ == "TrackerActions"


async def test_an_item_lattice_did_not_file_starts_a_chain_of_its_own(app: Following) -> None:
    await seeded(app)
    item = app.tracker.add(PROJECT, "Theirs")
    assert await app.poll()
    [created] = await app.published()
    assert created.correlation_id == created.id
    assert isinstance(created.event, ItemCreated)
    assert created.event.key is None
    assert item.key is None


async def test_a_chain_reflexr_no_longer_has_leaves_the_event_to_start_its_own(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock)
    await seeded(app)
    item = await app.filed("dead-letter/a")
    assert await app.poll()
    app.clock.advance(SECOND)
    app.tracker.edit(item, ItemFields(title="Renamed"))
    emptied = following(ledger, clock, tracker=app.tracker)  # reflexr's log, lost
    assert await emptied.poll()
    [changed] = await emptied.published()
    assert changed.correlation_id == changed.id


# ─── dead letters and projections ─────────────────────────────────────────────


async def test_a_projection_that_raises_dead_letters_its_event_once(
    ledger: Ledger, clock: FakeClock
) -> None:
    def project(event: TrackerEvent) -> reflexr.Event | None:
        if isinstance(event, ItemChanged) and event.new == "Poison":
            raise ValueError("no")
        return None if isinstance(event, ItemRemoved) else event

    app = following(ledger, clock, projections={KEY: project})
    item = app.tracker.add(PROJECT, "Filed")
    await seeded(app)
    app.tracker.edit(item, ItemFields(title="Poison", priority="high"))
    assert await app.poll()
    assert await app.poll()
    assert changes(await app.events()) == [("changed", item.id, "priority", "high")]
    [letter] = await ledger.tracker_dead_letters(KEY)
    assert letter == TrackerDeadLetter(
        event_id=letter.event_id,
        event_type="tracker:item_changed",
        item_id=item.id,
        error="ValueError: no",
    )
    app.tracker.delete(item)
    app.clock.advance(timedelta(days=1))
    assert await app.poll()
    assert len(await app.events()) == 1, "a projection returning None publishes nothing"


async def test_a_projection_returning_reflexrs_own_event_dead_letters_it(
    ledger: Ledger, clock: FakeClock
) -> None:
    def forged(event: TrackerEvent) -> reflexr.Event:
        return Tick(schedule="nightly", at=START)

    app = following(ledger, clock, projections={KEY: forged})
    await seeded(app)
    app.tracker.add(PROJECT, "Filed")
    assert await app.poll()
    [letter] = await ledger.tracker_dead_letters(KEY)
    assert letter.error.startswith("Forbidden: ")


async def test_a_type_reflexr_refuses_stops_the_follower(ledger: Ledger, clock: FakeClock) -> None:
    app = following(ledger, clock, projections={KEY: lambda event: Odd()})
    await seeded(app)
    app.tracker.add(PROJECT, "Filed")
    with pytest.raises(NotFound):
        await app.poll()


# ─── switched off, leases and failures ────────────────────────────────────────


async def test_a_switched_off_workspace_reads_and_writes_nothing(
    ledger: Ledger, clock: FakeClock
) -> None:
    switched: dict[str, bool] = {"on": False}

    async def enabled(tenant_id: str, workspace_id: str, key: str, /) -> bool:
        assert (tenant_id, workspace_id, key) == (*KEY, "tracker:fake")
        return switched["on"]

    app = following(ledger, clock, enabled=enabled)
    app.tracker.add(PROJECT, "Filed")
    assert not await app.poll()
    assert app.tenant.asked == [], "not even its credentials"
    assert await ledger.tracker_following(KEY) is None
    switched["on"] = True
    assert await app.poll()
    assert app.tenant.asked == [TENANT]


async def test_an_unbound_workspace_or_a_held_lease_is_not_read(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock)
    assert not await app.poll(WorkspaceKey(TENANT, "dev"))
    other = following(ledger, clock, tracker=app.tracker, holder="p2")
    assert await other.poll()
    assert not await app.poll(), "p2 holds the lease"
    clock.advance(timedelta(minutes=1))
    assert await app.poll(), "until it lapses"


async def test_a_trackers_failure_is_read_past(app: Following) -> None:
    item = app.tracker.add(PROJECT, "Filed")
    await seeded(app)
    app.tracker.edit(item, ItemFields(title="Renamed"))
    app.tracker.fail(Unavailable("down"))
    assert await app.poll()
    assert await app.events() == []
    app.tracker.fail(Unauthorized("rotated"))
    assert await app.poll()
    assert await app.poll(), "the next poll asks for the credentials again"
    assert app.tenant.asked == [TENANT, TENANT]
    assert changes(await app.events()) == [("changed", item.id, "title", "Renamed")]


# ─── two tenants ──────────────────────────────────────────────────────────────


async def test_two_tenants_never_read_each_others(ledger: Ledger, clock: FakeClock) -> None:
    """Phase 2: a two-tenant test never reads across tenants."""
    globex = WorkspaceKey("globex", "ops")
    acme_tracker, globex_tracker = FakeTracker(clock=clock), FakeTracker(clock=clock)
    acme = following(ledger, clock, tracker=acme_tracker)
    other = following(ledger, clock, tracker=globex_tracker, bindings={globex: BINDING})
    await seeded(acme)
    assert await other.poll(globex)
    acme_tracker.add(PROJECT, "Acme's")
    globex_tracker.add(PROJECT, "Globex's")
    assert await acme.poll()
    assert await other.poll(globex)
    assert changes(await acme.events()) == [("created", "item-1", "Acme's")]
    assert changes(await other.events(globex)) == [("created", "item-1", "Globex's")]
    assert [s.item["title"] for s in (await ledger.snapshots(KEY)).values()] == ["Acme's"]
    assert [s.item["title"] for s in (await ledger.snapshots(globex)).values()] == ["Globex's"]


# ─── the budget ───────────────────────────────────────────────────────────────


async def test_polls_stay_within_the_budget_under_a_write_burst(
    ledger: Ledger, clock: FakeClock
) -> None:
    """Phase 2: a tenant's polls stay within its budget under a write burst."""
    app = following(ledger, clock, budget=8)
    items = [app.tracker.add(PROJECT, f"Item {n}") for n in range(3)]
    await seeded(app)  # the list: 1
    for item in items:
        app.tracker.reply(item, "<p>A person's.</p>")
    filed = await app.filed("dead-letter/a")  # find and create: 3
    acting = await app.acting()
    for n in range(3):
        await acting.comment(filed, f"<p>Burst {n}.</p>")  # the burst spends first: 6
    assert await app.poll()  # the list and one item's comments: the budget's last two
    assert changes(await app.events()) == [("commented", items[0].id, "<p>A person's.</p>")]
    assert await app.poll()
    assert len(await app.events()) == 1, "no budget left: nothing read"
    clock.advance(timedelta(minutes=1))
    assert await app.poll()
    assert [c[1] for c in changes(await app.events())] == [item.id for item in items]


async def test_a_run_writing_to_one_item_in_a_loop_stops_at_the_cap(app: Following) -> None:
    """Phase 2: a rule writing to one item in a loop stops at the cap."""
    item = await app.filed("dead-letter/a")
    acting = await app.acting()
    for n in range(LOOP_CAP):
        await acting.comment(item, f"<p>Again {n}.</p>")
    with pytest.raises(RunFailure) as capped:
        await acting.set_state(item, "done")
    assert (capped.value.reason, capped.value.permanent) == ("tracker_loop", True)
    app.clock.advance(timedelta(hours=1))
    await acting.set_state(item, "done")
