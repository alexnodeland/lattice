"""What a run does in its tracker through `TrackerActions`: claims, keys, keyed edits, refusals.

Every test runs on every ledger, so the claims hold on memory, SQLite and PostgreSQL alike.
"""

from datetime import timedelta

import pytest

from reflexr.workspace import RunFailure
from relayr.ledger import Ledger
from relayr.outbound import Allowlist, NotAllowed
from relayr.trackers import (
    CLAIM_TTL,
    CREDENTIALS_TTL,
    Deleted,
    FakeTracker,
    ItemDraft,
    ItemFields,
    ItemRef,
    NotFound,
    RateLimited,
    Refused,
    TrackerActions,
    TrackerError,
    TrackerRefused,
    Unauthorized,
    Unavailable,
)
from tests.clock import FakeClock
from tests.trackers.conftest import (
    CREDENTIALS,
    KEY,
    PROJECT,
    SOURCE,
    Runs,
    Tenant,
    attempt,
    connector,
)

DRAFT = ItemDraft(title="A run failed", description="<p>It failed.</p>", labels=("run-failed",))
KEYED = "dead-letter/run_1"


async def filed(acting: TrackerActions, key: str = KEYED, draft: ItemDraft = DRAFT) -> ItemRef:
    item = await acting.ensure_item(draft, key=key)
    assert isinstance(item, ItemRef)
    return item


# ─── filing once ──────────────────────────────────────────────────────────────


async def test_an_item_is_filed_once_by_its_key(runs: Runs, tracker: FakeTracker) -> None:
    reaction = await runs.reaction()
    acting = runs.trackers.acting(reaction)
    assert runs.trackers.acting(reaction) is acting, "one per attempt"
    item = await filed(acting)
    assert await filed(acting) == item
    later = runs.trackers.acting(await runs.reaction())
    assert await filed(later) == item, "and for a later run, by the same key"
    [found] = tracker.items_in(PROJECT)
    assert (item.key, item.name, found.title) == (KEYED, "OPS-1", DRAFT.title)
    assert (found.priority, found.labels) == ("medium", ("lattice", "run-failed")), "the binding's"


async def test_a_draft_says_what_the_binding_otherwise_would(
    runs: Runs, tracker: FakeTracker
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    draft = ItemDraft(title="t", priority="urgent", state="todo", labels=("lattice", "x"))
    await filed(acting, draft=draft)
    [found] = tracker.items_in(PROJECT)
    assert (found.priority, found.state, found.labels) == ("urgent", "todo", ("lattice", "x"))


async def test_a_derived_key_files_once_per_run_however_often_it_is_retried(
    runs: Runs, tracker: FakeTracker
) -> None:
    reaction = await runs.reaction()
    first = await runs.trackers.acting(reaction).ensure_item(DRAFT)
    retried = runs.trackers.acting(await runs.reaction(attempt(reaction)))
    assert await retried.ensure_item(DRAFT) == first
    other = await runs.trackers.acting(await runs.reaction()).ensure_item(DRAFT)
    assert other != first, "another run files its own"
    assert tracker.created == 2


async def test_a_run_killed_between_create_and_record_makes_one_item(
    runs: Runs, tracker: FakeTracker, clock: FakeClock
) -> None:
    reaction = await runs.reaction()
    tracker.lose_next_created()
    with pytest.raises(RunFailure) as lost:
        await runs.trackers.acting(reaction).ensure_item(DRAFT, key=KEYED)
    assert (lost.value.reason, lost.value.permanent) == ("tracker_unavailable", False)
    retried = runs.trackers.acting(await runs.reaction(attempt(reaction)))
    with pytest.raises(RunFailure) as held:
        await retried.ensure_item(DRAFT, key=KEYED)
    assert (held.value.reason, held.value.permanent) == ("tracker_claimed", False)
    clock.advance(CLAIM_TTL)
    again = runs.trackers.acting(await runs.reaction(attempt(reaction)))
    item = await filed(again)
    assert tracker.created == 1, "the claim, taken again, found the item it made"
    assert [i.ref.id for i in tracker.items_in(PROJECT)] == [item.id]


async def test_a_deleted_item_is_not_filed_again(runs: Runs, tracker: FakeTracker) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    item = await filed(acting)
    tracker.delete(item)
    assert await acting.ensure_item(DRAFT, key=KEYED) == Deleted(key=KEYED)
    tracker.fail(Unavailable("not asked"))
    later = runs.trackers.acting(await runs.reaction())
    assert await later.ensure_item(DRAFT, key=KEYED) == Deleted(key=KEYED), "from the ledger"
    assert tracker.created == 1
    assert await later.filed(KEYED) is None


async def test_a_closed_or_archived_item_is_returned(runs: Runs, tracker: FakeTracker) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    item = await filed(acting)
    tracker.edit(item, ItemFields(state="done"))
    tracker.archive(item)
    assert await filed(acting) == item, "for the rule to reopen if it will"
    assert await acting.filed(KEYED) == item


# ─── comments ─────────────────────────────────────────────────────────────────


async def test_a_comment_is_posted_once(runs: Runs, tracker: FakeTracker) -> None:
    reaction = await runs.reaction()
    acting = runs.trackers.acting(reaction)
    item = await filed(acting)
    comment = await acting.comment(item, "Retried 3 times")
    retried = runs.trackers.acting(await runs.reaction(attempt(reaction)))
    assert await retried.comment(item, "Retried 3 times") == comment
    keyed = await acting.comment(item, "Once", key="note")
    assert await retried.comment(item, "Once more", key="note") == keyed
    later = runs.trackers.acting(await runs.reaction())
    await later.comment(item, "Retried 3 times")
    connection = tracker.connect(CREDENTIALS, SOURCE)
    bodies = [c.body for c in await connection.comments(item, None)]
    assert bodies == ["Retried 3 times", "Once", "Retried 3 times"], "a later run's is its own"


async def test_a_comment_lost_on_its_way_is_found_by_its_key(
    runs: Runs, tracker: FakeTracker, clock: FakeClock
) -> None:
    reaction = await runs.reaction()
    acting = runs.trackers.acting(reaction)
    item = await filed(acting)
    tracker.fail(Unavailable("timed out"))
    with pytest.raises(RunFailure, match="timed out"):
        await acting.comment(item, "hello", key="hi")
    retried = runs.trackers.acting(await runs.reaction(attempt(reaction)))
    with pytest.raises(RunFailure) as held:
        await retried.comment(item, "hello", key="hi")
    assert held.value.reason == "tracker_claimed"
    clock.advance(CLAIM_TTL)
    comment = await retried.comment(item, "hello", key="hi")
    assert comment.item == item.id


# ─── keyed edits ──────────────────────────────────────────────────────────────


async def test_an_edit_sends_only_what_differs_and_records_it_first(
    runs: Runs, tracker: FakeTracker, ledger: Ledger
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    item = await filed(acting)
    before = (await acting.read(item) or pytest.fail("filed")).updated_at
    await acting.update(item, ItemFields(title=DRAFT.title, labels=("run-failed", "lattice")))
    assert (await acting.read(item) or pytest.fail("filed")).updated_at == before, "nothing sent"
    await acting.set_state(item, "started")
    await acting.update(item, ItemFields(priority="urgent", labels=("lattice",)))
    tracked = await ledger.tracked(KEY, "item", KEYED)
    assert tracked is not None
    assert tracked.written == {"state": "started", "priority": "urgent", "labels": ["lattice"]}
    found = await acting.read(item)
    assert found is not None
    assert (found.state, found.priority, found.labels) == ("started", "urgent", ("lattice",))


async def test_an_edit_the_tracker_refuses_forgets_its_record(
    runs: Runs, tracker: FakeTracker, ledger: Ledger
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    item = await filed(acting)
    await acting.set_state(item, "started")
    tracker.fail(None, Refused("no such state"))
    with pytest.raises(TrackerRefused) as refused:
        await acting.update(item, ItemFields(state="done", title="renamed"))
    assert (refused.value.reason, refused.value.permanent) == ("tracker_refused", False)
    tracked = await ledger.tracked(KEY, "item", KEYED)
    assert tracked is not None
    assert tracked.written == {"state": "started"}


async def test_an_edit_of_a_deleted_item_is_refused_and_marks_it(
    runs: Runs, tracker: FakeTracker
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    item = await filed(acting)
    tracker.delete(item)
    with pytest.raises(TrackerRefused) as refused:
        await acting.set_state(item, "done")
    assert refused.value.reason == "tracker_not_found"
    assert await acting.ensure_item(DRAFT, key=KEYED) == Deleted(key=KEYED)


async def test_only_the_items_lattice_filed_are_edited(runs: Runs, tracker: FakeTracker) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    theirs = tracker.add(PROJECT, "a person's")
    with pytest.raises(RunFailure) as refused:
        await acting.set_state(theirs, "done")
    assert (refused.value.reason, refused.value.permanent) == ("tracker_not_filed", True)
    await acting.comment(theirs, "but commented on")


# ─── refusals ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("error", "reason", "permanent"),
    [
        (RateLimited(30), "tracker_rate_limited", False),
        (Unavailable("down"), "tracker_unavailable", False),
        (Refused("invalid"), "tracker_refused", False),
        (NotFound("gone"), "tracker_not_found", False),
    ],
)
async def test_the_trackers_errors_fail_the_attempt(
    runs: Runs, tracker: FakeTracker, error: TrackerError, reason: str, permanent: bool
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    tracker.fail(error)
    with pytest.raises(RunFailure) as failed:
        await acting.ensure_item(DRAFT, key=KEYED)
    assert (failed.value.reason, failed.value.permanent) == (reason, permanent)


async def test_a_refused_key_asks_for_the_credentials_again_once(
    runs: Runs, tracker: FakeTracker, tenant: Tenant
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    await filed(acting)
    tracker.rotate("rotated")
    tenant.credentials = CREDENTIALS.model_copy(update={"api_key": "rotated"})
    await filed(acting)
    assert tenant.asked == ["acme", "acme"], "asked again after the tracker refused the key"
    tracker.rotate("revoked")
    with pytest.raises(RunFailure) as failed:
        await filed(acting)
    assert (failed.value.reason, failed.value.permanent) == ("tracker_unauthorized", True)
    tracker.fail(Unauthorized("stale"))
    tracker.rotate("rotated")
    await filed(acting)


async def test_credentials_are_kept_five_minutes(
    runs: Runs, tenant: Tenant, clock: FakeClock
) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    await filed(acting)
    clock.advance(CREDENTIALS_TTL - timedelta(seconds=1))
    await filed(acting)
    assert len(tenant.asked) == 1
    clock.advance(timedelta(seconds=1))
    await filed(acting)
    assert len(tenant.asked) == 2


async def test_a_rule_writes_only_if_its_allowlist_says(
    runs: Runs, ledger: Ledger, tracker: FakeTracker, tenant: Tenant, clock: FakeClock
) -> None:
    reaction = await runs.reaction()
    refused = connector(ledger, tracker, tenant, clock, allowlists={"ops:*": Allowlist()})
    unbound = connector(ledger, tracker, tenant, clock, bindings={})
    for acting in (refused.acting(reaction), unbound.acting(reaction)):
        for write in (
            acting.ensure_item(DRAFT),
            acting.filed(KEYED),
            acting.link(ItemRef(project=PROJECT, id="1", number=1, name="OPS-1")),
        ):
            with pytest.raises(NotAllowed):
                await write
    assert tracker.created == 0
    with pytest.raises(ValueError, match="allowlist's key"):
        connector(ledger, tracker, tenant, clock, allowlists={"reflexr:*": Allowlist()})


async def test_a_link_is_the_trackers(runs: Runs) -> None:
    acting = runs.trackers.acting(await runs.reaction())
    item = await filed(acting)
    assert await acting.link(item) == "https://tracker.test/ops/1"
