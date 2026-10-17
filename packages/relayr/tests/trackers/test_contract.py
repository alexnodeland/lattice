"""The tracker port's contract, which every adapter keeps (lattice RFC-0004).

It runs against the fake, and against Vikunja's and Plane's recorded exchanges, or a live Vikunja
or Plane (`tests/trackers/harnesses.py` says how each is made).
"""

from collections.abc import AsyncIterator

import pytest

from relayr.trackers import CommentRef, Item, ItemDraft, ItemFields, ItemRef, NotFound
from tests.trackers.harnesses import Harness, fake, plane, vikunja

KEY = "dead-letter/run_1"
DRAFT = ItemDraft(
    title="A run failed",
    description="<p>It failed.</p>",
    state="todo",
    priority="high",
    labels=("lattice", "run-failed"),
)


async def _made(request: pytest.FixtureRequest) -> AsyncIterator[Harness]:
    match request.param:
        case "fake":
            context = fake()
        case "plane":
            context = plane(request.node.originalname)
        case _:
            context = vikunja(request.node.originalname)
    async with context as made:
        yield made


@pytest.fixture(params=["fake", "plane", "vikunja"])
async def harness(request: pytest.FixtureRequest) -> AsyncIterator[Harness]:
    async for made in _made(request):
        yield made


@pytest.fixture(params=["fake", "plane"])
async def plane_like(request: pytest.FixtureRequest) -> AsyncIterator[Harness]:
    """A tracker that keeps external ids and archives items, as Plane does and Vikunja doesn't."""
    async for made in _made(request):
        yield made


async def read(harness: Harness, ref: ItemRef) -> Item:
    item = await harness.tracker.item(ref)
    assert item is not None
    return item


async def test_an_item_is_filed_by_its_key_and_found_by_it(harness: Harness) -> None:
    tracker, project = harness.tracker, harness.project
    assert await tracker.find(project, KEY) is None
    ref = await tracker.create(project, KEY, DRAFT)
    assert ref.key == KEY
    assert await tracker.find(project, KEY) == ref
    assert await tracker.find(project, "another") is None
    item = await read(harness, ref)
    assert item.ref == ref
    assert (item.title, item.description) == (DRAFT.title, DRAFT.description)
    assert (item.state, item.priority, item.labels) == ("todo", "high", DRAFT.labels)
    assert tracker.link(ref) == harness.link(ref)


async def test_a_key_is_found_whole_not_by_its_start(harness: Harness) -> None:
    longer = await harness.tracker.create(harness.project, f"{KEY}0", DRAFT)
    assert await harness.tracker.find(harness.project, KEY) is None
    ref = await harness.tracker.create(harness.project, KEY, DRAFT)
    assert await harness.tracker.find(harness.project, KEY) == ref
    assert await harness.tracker.find(harness.project, f"{KEY}0") == longer


async def test_a_persons_item_and_comment_have_no_key(harness: Harness) -> None:
    theirs = await harness.add("Filed by hand")
    item = await read(harness, theirs)
    assert (item.ref, item.title) == (theirs, "Filed by hand")
    assert item.ref.key is None
    await harness.reply(theirs, "<p>Mine.</p>")
    await harness.tracker.comment(theirs, "ours", "<p>Ours.</p>")
    comments = await harness.tracker.comments(theirs, None)
    assert [(c.key, c.body) for c in comments] == [(None, "<p>Mine.</p>"), ("ours", "<p>Ours.</p>")]


async def test_a_change_to_a_deleted_item_is_not_found(harness: Harness) -> None:
    ref = await harness.tracker.create(harness.project, KEY, DRAFT)
    await harness.delete(ref)
    with pytest.raises(NotFound):
        await harness.tracker.update(ref, ItemFields(title="Too late"))
    with pytest.raises(NotFound):
        await harness.tracker.comment(ref, "late", "<p>Too late.</p>")


async def test_a_key_already_used_files_nothing_more(plane_like: Harness) -> None:
    harness = plane_like
    ref = await harness.tracker.create(harness.project, KEY, DRAFT)
    again = await harness.tracker.create(
        harness.project, KEY, DRAFT.model_copy(update={"title": "x"})
    )
    assert again == ref


async def test_an_update_sets_only_the_fields_given(harness: Harness) -> None:
    tracker = harness.tracker
    ref = await tracker.create(harness.project, KEY, DRAFT)
    before = await read(harness, ref)
    await harness.tick()
    await tracker.update(ref, ItemFields(state="done", labels=("lattice", "triaged")))
    item = await read(harness, ref)
    assert (item.state, item.labels) == ("done", ("lattice", "triaged"))
    assert (item.title, item.description, item.priority) == (DRAFT.title, DRAFT.description, "high")
    assert item.updated_at > before.updated_at
    await tracker.update(
        ref, ItemFields(title="Renamed", description="<p>Again.</p>", priority="low")
    )
    item = await read(harness, ref)
    assert (item.title, item.description, item.priority) == ("Renamed", "<p>Again.</p>", "low")
    assert item.ref.key == KEY, "the key outlives a new description"


async def test_a_comment_is_posted_once_by_its_key(harness: Harness) -> None:
    tracker = harness.tracker
    ref = await tracker.create(harness.project, KEY, DRAFT)
    first = await tracker.comment(ref, "first", "<p>Retried 3 times.</p>")
    assert await tracker.comment(ref, "first", "<p>Retried 3 times.</p>") == first
    second = await tracker.comment(ref, "second", "<p>Retried 4 times.</p>")
    comments = await tracker.comments(ref, None)
    assert [(c.ref, c.key, c.body) for c in comments] == [
        (first, "first", "<p>Retried 3 times.</p>"),
        (second, "second", "<p>Retried 4 times.</p>"),
    ]
    assert [c.ref for c in await tracker.comments(ref, first)] == [second]
    assert await tracker.comments(ref, second) == []
    assert isinstance(first, CommentRef)


async def test_items_are_read_after_a_cursor_oldest_first(harness: Harness) -> None:
    tracker, project = harness.tracker, harness.project
    first = await tracker.create(project, "one", DRAFT)
    await harness.tick()
    second = await tracker.create(project, "two", DRAFT)
    page = await tracker.items(project, None)
    assert [item.ref for item in page.items] == [first, second]
    assert page.next is not None
    assert (page.next.updated_at, page.next.id) == (page.items[-1].updated_at, second.id)
    assert (await tracker.items(project, page.next)).items == ()
    await harness.tick()
    await tracker.update(first, ItemFields(title="Changed"))
    changed = await tracker.items(project, page.next)
    assert [item.ref for item in changed.items] == [first]
    assert (await tracker.items(project, changed.next)).next == changed.next


async def test_a_deleted_item_is_gone(harness: Harness) -> None:
    ref = await harness.tracker.create(harness.project, KEY, DRAFT)
    await harness.delete(ref)
    assert await harness.tracker.item(ref) is None
    assert await harness.tracker.find(harness.project, KEY) is None


async def test_an_archived_item_is_read_but_not_listed(plane_like: Harness) -> None:
    harness = plane_like
    assert harness.archive is not None
    ref = await harness.tracker.create(harness.project, KEY, DRAFT)
    harness.archive(ref)
    assert (await read(harness, ref)).ref == ref
    assert await harness.tracker.find(harness.project, KEY) == ref
    assert (await harness.tracker.items(harness.project, None)).items == ()


async def test_a_nudge_is_a_signed_webhooks_project(harness: Harness) -> None:
    headers, body = harness.delivery
    nudge = harness.tracker.nudge(headers, body)
    assert nudge is not None
    assert nudge.project == harness.delivered
    assert harness.tracker.nudge(headers, body + b" ") is None, "the bytes it signed, only"
    assert harness.tracker.nudge({}, body) is None
