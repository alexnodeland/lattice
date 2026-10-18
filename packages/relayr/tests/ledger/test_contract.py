"""The ledger's contract, which every adapter passes: leases, cursors, dead letters, causes,
tracker keys, and what the tracker followers read."""

from datetime import timedelta

from relayr.ledger import (
    Cause,
    DeadLetter,
    Ledger,
    Snapshot,
    Tracked,
    TrackedKey,
    TrackedKind,
    TrackerDeadLetter,
    TrackerFollowing,
    WorkspaceKey,
)
from tests.clock import START, FakeClock

PROD = WorkspaceKey("acme", "prod")
STAGING = WorkspaceKey("acme", "staging")
OTHER = WorkspaceKey("globex", "prod")
TTL = timedelta(seconds=30)


def letter(seq: int, error: str = "ValueError: no") -> DeadLetter:
    return DeadLetter(seq=seq, envelope_id=f"evt_{seq}", event_type="app_event", error=error)


async def test_a_workspace_starts_with_nothing(ledger: Ledger) -> None:
    assert await ledger.cursor(PROD) == 0
    assert await ledger.dead_letters(PROD) == []
    assert await ledger.followed() == []


async def test_one_holder_at_a_time_holds_a_lease(ledger: Ledger) -> None:
    assert await ledger.acquire_lease(PROD, "a", TTL)
    assert not await ledger.acquire_lease(PROD, "b", TTL)
    assert await ledger.acquire_lease(PROD, "a", TTL), "its holder renews it"
    assert await ledger.acquire_lease(STAGING, "b", TTL), "each workspace has its own"
    assert await ledger.acquire_lease(OTHER, "b", TTL), "and so does each tenant's"


async def test_a_released_lease_is_free(ledger: Ledger) -> None:
    await ledger.acquire_lease(PROD, "a", TTL)
    await ledger.release_lease(PROD, "b")
    assert not await ledger.acquire_lease(PROD, "b", TTL), "only its holder releases it"
    await ledger.release_lease(PROD, "a")
    assert await ledger.acquire_lease(PROD, "b", TTL)
    await ledger.release_lease(STAGING, "a")  # a workspace the ledger doesn't know


async def test_a_lease_lapses_unless_it_is_renewed(ledger: Ledger, clock: FakeClock) -> None:
    await ledger.acquire_lease(PROD, "a", TTL)
    clock.advance(TTL - timedelta(seconds=1))
    assert not await ledger.acquire_lease(PROD, "b", TTL)
    assert await ledger.acquire_lease(PROD, "a", TTL)
    clock.advance(TTL)
    assert await ledger.acquire_lease(PROD, "b", TTL)
    assert not await ledger.acquire_lease(PROD, "a", TTL)


async def test_a_cursor_only_moves_forward(ledger: Ledger) -> None:
    await ledger.save_cursor(PROD, 5)
    await ledger.save_cursor(PROD, 3)
    assert await ledger.cursor(PROD) == 5
    await ledger.save_cursor(PROD, 8)
    assert await ledger.cursor(PROD) == 8
    assert await ledger.cursor(STAGING) == 0
    assert await ledger.cursor(OTHER) == 0


async def test_a_lease_keeps_the_cursor(ledger: Ledger) -> None:
    await ledger.save_cursor(PROD, 5)
    await ledger.acquire_lease(PROD, "a", TTL)
    await ledger.release_lease(PROD, "a")
    assert await ledger.cursor(PROD) == 5


async def test_followed_workspaces_are_those_with_a_lease_or_a_cursor(ledger: Ledger) -> None:
    await ledger.save_cursor(STAGING, 1)
    await ledger.acquire_lease(OTHER, "a", TTL)
    await ledger.acquire_lease(PROD, "a", TTL)
    await ledger.release_lease(PROD, "a")
    await ledger.dead_letter(WorkspaceKey("acme", "dev"), letter(1))
    assert await ledger.followed() == [PROD, STAGING, OTHER]


async def test_dead_letters_are_kept_once_per_seq_in_order(ledger: Ledger) -> None:
    await ledger.dead_letter(PROD, letter(7))
    await ledger.dead_letter(PROD, letter(2))
    await ledger.dead_letter(PROD, letter(7, "ValueError: again"))
    await ledger.dead_letter(STAGING, letter(1))
    assert await ledger.dead_letters(PROD) == [letter(2), letter(7)]
    assert await ledger.dead_letters(STAGING) == [letter(1)]
    assert await ledger.dead_letters(OTHER) == []


CAUSE = Cause(correlation_id="evt_1", firing_id="fir_1", run_id="fir_1", depth=1)


async def test_a_cause_is_kept_once_per_key(ledger: Ledger) -> None:
    later = CAUSE.model_copy(update={"run_id": "fir_2"})
    await ledger.record_cause(PROD, "message", "7", CAUSE)
    await ledger.record_cause(PROD, "message", "7", later)
    await ledger.record_cause(PROD, "proposal", "7", later)
    assert await ledger.cause(PROD, "message", "7") == CAUSE
    assert await ledger.cause(PROD, "proposal", "7") == later
    assert await ledger.cause(PROD, "turn", "7") is None
    assert await ledger.cause(STAGING, "message", "7") is None
    assert await ledger.followed() == [], "a cause follows no workspace"


async def test_causes_are_forgotten_once_older_than_a_time(
    ledger: Ledger, clock: FakeClock
) -> None:
    await ledger.record_cause(PROD, "message", "old", CAUSE)
    await ledger.record_cause(STAGING, "message", "old", CAUSE)
    clock.advance(timedelta(hours=1))
    await ledger.record_cause(PROD, "message", "new", CAUSE)
    await ledger.forget_causes(PROD, older_than=timedelta(minutes=30))
    assert await ledger.cause(PROD, "message", "old") is None
    assert await ledger.cause(PROD, "message", "new") == CAUSE
    assert await ledger.cause(STAGING, "message", "old") == CAUSE, "only that workspace's"


STALE = timedelta(seconds=30)
REF = {"project": "ops", "id": "7", "number": 7, "key": "dead-letter/run_1"}


async def test_a_key_is_claimed_once_until_its_claim_goes_stale(
    ledger: Ledger, clock: FakeClock
) -> None:
    assert await ledger.tracked(PROD, "item", "k") is None
    assert await ledger.claim_tracked(PROD, "item", "k", "evt_1", stale_after=STALE)
    assert not await ledger.claim_tracked(PROD, "item", "k", "evt_2", stale_after=STALE)
    assert await ledger.claim_tracked(PROD, "comment", "k", "evt_2", stale_after=STALE)
    assert await ledger.claim_tracked(STAGING, "item", "k", "evt_2", stale_after=STALE)
    clock.advance(STALE - timedelta(seconds=1))
    assert not await ledger.claim_tracked(PROD, "item", "k", "evt_2", stale_after=STALE)
    clock.advance(timedelta(seconds=1))
    assert await ledger.claim_tracked(PROD, "item", "k", "evt_2", stale_after=STALE)
    assert not await ledger.claim_tracked(PROD, "item", "k", "evt_3", stale_after=STALE), (
        "a claim taken again is fresh"
    )
    assert await ledger.tracked(PROD, "item", "k") == Tracked(correlation_id="evt_1")
    assert await ledger.followed() == [], "a tracker key follows no workspace"


async def test_a_recorded_key_is_never_claimed_again(ledger: Ledger, clock: FakeClock) -> None:
    await ledger.claim_tracked(PROD, "item", "k", "evt_1", stale_after=STALE)
    assert await ledger.record_tracked(PROD, "item", "k", REF) == REF
    other = REF | {"id": "8"}
    assert await ledger.record_tracked(PROD, "item", "k", other) == REF, "the first is kept"
    clock.advance(STALE * 10)
    assert not await ledger.claim_tracked(PROD, "item", "k", "evt_2", stale_after=STALE)
    assert await ledger.tracked(PROD, "item", "k") == Tracked(correlation_id="evt_1", ref=REF)
    assert await ledger.tracked(PROD, "comment", "k") is None


async def test_a_released_claim_is_free_and_a_recorded_key_is_not_released(
    ledger: Ledger,
) -> None:
    await ledger.claim_tracked(PROD, "item", "k", "evt_1", stale_after=STALE)
    await ledger.release_tracked(PROD, "item", "k")
    assert await ledger.tracked(PROD, "item", "k") is None
    assert await ledger.claim_tracked(PROD, "item", "k", "evt_2", stale_after=STALE)
    await ledger.record_tracked(PROD, "item", "k", REF)
    await ledger.release_tracked(PROD, "item", "k")
    await ledger.release_tracked(PROD, "comment", "k")
    assert await ledger.tracked(PROD, "item", "k") == Tracked(correlation_id="evt_2", ref=REF)


async def test_a_key_never_claimed_records_nothing(ledger: Ledger) -> None:
    assert await ledger.record_tracked(PROD, "item", "k", REF) is None
    await ledger.mark_tracked_deleted(PROD, "k")
    await ledger.record_written(PROD, "k", {"state": "done"})
    await ledger.forget_written(PROD, "k", ["state"])
    assert await ledger.tracked(PROD, "item", "k") is None


async def test_an_item_keeps_the_values_relayr_last_set(ledger: Ledger) -> None:
    await ledger.claim_tracked(PROD, "item", "k", "evt_1", stale_after=STALE)
    await ledger.claim_tracked(PROD, "comment", "k", "evt_1", stale_after=STALE)
    await ledger.record_written(PROD, "k", {"state": "todo", "priority": "high"})
    await ledger.record_written(PROD, "k", {"state": "done", "labels": ["lattice"]})
    await ledger.forget_written(PROD, "k", ["priority", "title"])
    tracked = await ledger.tracked(PROD, "item", "k")
    assert tracked is not None
    assert tracked.written == {"state": "done", "labels": ["lattice"]}
    assert await ledger.tracked(PROD, "comment", "k") == Tracked(correlation_id="evt_1")


async def test_every_key_of_a_workspace_is_read_by_kind_then_key(ledger: Ledger) -> None:
    assert await ledger.every_tracked(PROD) == {}
    claims: list[tuple[TrackedKind, str, str]] = [
        ("item", "b", "evt_1"),
        ("comment", "c", "evt_2"),
        ("item", "a", "evt_3"),
    ]
    for kind, key, chain in claims:
        await ledger.claim_tracked(PROD, kind, key, chain, stale_after=STALE)
    await ledger.claim_tracked(STAGING, "item", "z", "evt_4", stale_after=STALE)
    await ledger.claim_tracked(OTHER, "item", "y", "evt_5", stale_after=STALE)
    await ledger.record_tracked(PROD, "item", "b", REF)
    await ledger.mark_tracked_deleted(PROD, "b")
    every = await ledger.every_tracked(PROD)
    assert list(every) == [
        TrackedKey("comment", "c"),
        TrackedKey("item", "a"),
        TrackedKey("item", "b"),
    ]
    assert every[TrackedKey("item", "b")] == Tracked(correlation_id="evt_1", ref=REF, deleted=True)
    assert every[TrackedKey("item", "a")] == Tracked(correlation_id="evt_3"), "a claim alone"
    assert list(await ledger.every_tracked(OTHER)) == [TrackedKey("item", "y")]


async def test_a_deleted_item_stays_deleted(ledger: Ledger) -> None:
    await ledger.claim_tracked(PROD, "item", "k", "evt_1", stale_after=STALE)
    await ledger.record_tracked(PROD, "item", "k", REF)
    await ledger.mark_tracked_deleted(PROD, "k")
    tracked = await ledger.tracked(PROD, "item", "k")
    assert tracked == Tracked(correlation_id="evt_1", ref=REF, deleted=True)


async def test_written_values_are_consumed_only_while_they_hold(ledger: Ledger) -> None:
    await ledger.consume_written(PROD, "k", {"state": "done"})  # a key never claimed
    await ledger.claim_tracked(PROD, "item", "k", "evt_1", stale_after=STALE)
    await ledger.record_written(PROD, "k", {"state": "done", "priority": "high", "title": "T"})
    await ledger.consume_written(PROD, "k", {"state": "done", "priority": "low"})
    tracked = await ledger.tracked(PROD, "item", "k")
    assert tracked is not None
    assert tracked.written == {"priority": "high", "title": "T"}, "a newer value is kept"


async def test_writes_to_an_item_are_counted_within_a_window(
    ledger: Ledger, clock: FakeClock
) -> None:
    hour = timedelta(hours=1)
    assert await ledger.record_tracker_write(PROD, "7", within=hour) == 1
    clock.advance(timedelta(minutes=40))
    assert await ledger.record_tracker_write(PROD, "7", within=hour) == 2
    assert await ledger.record_tracker_write(PROD, "8", within=hour) == 1, "each item its own"
    assert await ledger.record_tracker_write(STAGING, "7", within=hour) == 1
    clock.advance(timedelta(minutes=30))
    assert await ledger.record_tracker_write(PROD, "7", within=hour) == 2, "the first lapsed"
    assert await ledger.snapshots(PROD) == {}, "a write is no snapshot"


async def test_writes_to_each_item_are_read_within_a_window(
    ledger: Ledger, clock: FakeClock
) -> None:
    hour = timedelta(hours=1)
    assert await ledger.tracker_writes(PROD, within=hour) == {}
    for _ in range(3):
        await ledger.record_tracker_write(PROD, "8", within=hour)
    await ledger.record_tracker_write(PROD, "7", within=hour)
    await ledger.record_tracker_write(STAGING, "7", within=hour)
    await ledger.save_snapshots(PROD, [snapshot("9")])
    assert await ledger.tracker_writes(PROD, within=hour) == {"7": 1, "8": 3}, (
        "by item, none left out"
    )
    clock.advance(timedelta(minutes=30))
    await ledger.record_tracker_write(PROD, "7", within=hour)
    clock.advance(timedelta(minutes=31))
    assert await ledger.tracker_writes(PROD, within=hour) == {"7": 1}, "the earlier lapsed"
    assert await ledger.tracker_writes(PROD, within=hour * 2) == {"7": 2, "8": 3}
    assert await ledger.tracker_writes(OTHER, within=hour) == {}


async def test_a_tracker_lease_is_apart_from_the_followers(
    ledger: Ledger, clock: FakeClock
) -> None:
    assert await ledger.acquire_lease(PROD, "a", TTL)
    assert await ledger.acquire_tracker_lease(PROD, "b", TTL), "the artifactr follower's is apart"
    assert not await ledger.acquire_tracker_lease(PROD, "a", TTL)
    assert await ledger.acquire_tracker_lease(PROD, "b", TTL), "its holder renews it"
    assert await ledger.acquire_tracker_lease(OTHER, "a", TTL)
    await ledger.release_tracker_lease(PROD, "a")
    assert not await ledger.acquire_tracker_lease(PROD, "a", TTL), "only its holder releases it"
    await ledger.release_tracker_lease(PROD, "b")
    assert await ledger.acquire_tracker_lease(PROD, "a", TTL)
    clock.advance(TTL)
    assert await ledger.acquire_tracker_lease(PROD, "b", TTL), "it lapses unless renewed"
    await ledger.release_tracker_lease(STAGING, "a")  # a workspace the ledger doesn't know
    assert await ledger.followed() == [PROD], "a tracker lease follows no artifactr workspace"


def following(
    project: str = "ops",
    cursor: tuple[int, str] | None = None,
    swept: int = 0,
    read: int | None = None,
) -> TrackerFollowing:
    at = None if cursor is None else (START + timedelta(seconds=cursor[0]), cursor[1])
    return TrackerFollowing(
        project=project,
        cursor=at,
        swept_at=START + timedelta(seconds=swept),
        read_at=None if read is None else START + timedelta(seconds=read),
    )


async def test_how_far_a_tracker_follower_read_only_moves_forward(ledger: Ledger) -> None:
    assert await ledger.tracker_following(PROD) is None
    await ledger.acquire_tracker_lease(PROD, "a", TTL)
    assert await ledger.tracker_following(PROD) is None, "a lease reads nothing"
    await ledger.save_tracker_following(PROD, following())
    assert await ledger.tracker_following(PROD) == following(), "an empty project has no cursor"
    await ledger.save_tracker_following(PROD, following(cursor=(5, "b"), swept=10))
    await ledger.save_tracker_following(PROD, following(cursor=(5, "a"), swept=3))
    await ledger.save_tracker_following(PROD, following(swept=4))
    assert await ledger.tracker_following(PROD) == following(cursor=(5, "b"), swept=10)
    await ledger.save_tracker_following(PROD, following(cursor=(6, "a"), swept=11))
    assert await ledger.tracker_following(PROD) == following(cursor=(6, "a"), swept=11)
    await ledger.save_tracker_following(PROD, following("dev", swept=1))
    assert await ledger.tracker_following(PROD) == following("dev", swept=1), "another project"
    assert await ledger.tracker_following(STAGING) is None
    assert await ledger.tracker_following(OTHER) is None


async def test_when_a_tracker_follower_last_read_only_moves_forward(ledger: Ledger) -> None:
    await ledger.save_tracker_following(PROD, following(read=20))
    await ledger.save_tracker_following(PROD, following(read=10))
    await ledger.save_tracker_following(PROD, following())
    assert await ledger.tracker_following(PROD) == following(read=20), "a read never goes back"
    await ledger.save_tracker_following(PROD, following(read=30))
    assert await ledger.tracker_following(PROD) == following(read=30)
    await ledger.save_tracker_following(PROD, following("dev", read=5))
    assert await ledger.tracker_following(PROD) == following("dev", read=5), "another project"


def snapshot(item_id: str, title: str = "T", comments: int | None = None) -> Snapshot:
    after = None if comments is None else START + timedelta(seconds=comments)
    return Snapshot(item_id=item_id, item={"title": title}, comments_after=after)


async def test_snapshots_replace_those_before_and_are_forgotten(ledger: Ledger) -> None:
    assert await ledger.snapshots(PROD) == {}
    await ledger.record_tracker_write(PROD, "2", within=TTL)
    await ledger.save_snapshots(PROD, [snapshot("1"), snapshot("2", comments=1)])
    await ledger.save_snapshots(PROD, [snapshot("2", "U", comments=2), snapshot("3")])
    await ledger.save_snapshots(STAGING, [snapshot("1", "S")])
    await ledger.save_snapshots(PROD, [])
    assert await ledger.snapshots(PROD) == {
        "1": snapshot("1"),
        "2": snapshot("2", "U", comments=2),
        "3": snapshot("3"),
    }
    assert await ledger.snapshots(PROD, ["2", "4"]) == {"2": snapshot("2", "U", comments=2)}
    assert await ledger.snapshots(PROD, []) == {}
    assert await ledger.record_tracker_write(PROD, "2", within=TTL) == 2, "a snapshot keeps writes"
    await ledger.forget_snapshots(PROD, ["2", "4"])
    assert await ledger.snapshots(PROD) == {"1": snapshot("1"), "3": snapshot("3")}
    assert await ledger.record_tracker_write(PROD, "2", within=TTL) == 1, "and forgets them"
    await ledger.forget_snapshots(PROD)
    assert await ledger.snapshots(PROD) == {}
    assert await ledger.snapshots(STAGING) == {"1": snapshot("1", "S")}


async def test_a_bound_project_of_many_items_is_saved_whole(ledger: Ledger) -> None:
    many = [snapshot(f"item-{n:04}") for n in range(1200)]
    await ledger.save_snapshots(PROD, many)
    assert len(await ledger.snapshots(PROD)) == 1200
    wanted = [s.item_id for s in many[::2]]
    assert sorted(await ledger.snapshots(PROD, wanted)) == wanted
    await ledger.forget_snapshots(PROD, wanted)
    assert len(await ledger.snapshots(PROD)) == 600


def tracker_letter(event_id: str, error: str = "ValueError: no") -> TrackerDeadLetter:
    return TrackerDeadLetter(
        event_id=event_id, event_type="tracker:item_changed", item_id="7", error=error
    )


async def test_tracker_dead_letters_are_kept_once_per_event_id(ledger: Ledger) -> None:
    await ledger.tracker_dead_letter(PROD, tracker_letter("trk_b"))
    await ledger.tracker_dead_letter(PROD, tracker_letter("trk_a"))
    await ledger.tracker_dead_letter(PROD, tracker_letter("trk_b", "ValueError: again"))
    await ledger.tracker_dead_letter(STAGING, tracker_letter("trk_c"))
    assert await ledger.tracker_dead_letters(PROD) == [
        tracker_letter("trk_a"),
        tracker_letter("trk_b"),
    ]
    assert await ledger.tracker_dead_letters(STAGING) == [tracker_letter("trk_c")]
    assert await ledger.tracker_dead_letters(OTHER) == []
    assert await ledger.dead_letters(PROD) == [], "apart from the artifactr follower's"
