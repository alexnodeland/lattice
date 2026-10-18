"""Reading back, as a state machine: people and runs change a fake tracker's items, comment and
delete, time passes, and the follower polls.

Whatever the order, lattice RFC-0004's "Reading back" and "Echoes and loops" hold at each poll:
the first publishes nothing; each later one publishes every field a person changed since the
last, as it now is, and every comment a person posted, and nothing relayr wrote; a sweep
publishes what left the list; a poll read again publishes nothing; and an event whose
projection raises is dead-lettered, once, and never published.

People and runs set values apart, so what relayr wrote can be told from what a person did.
"""

import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, precondition, rule
from pydantic import JsonValue

import reflexr
from reflexr.workspace import RunFailure
from relayr.ledger import InMemoryLedger
from relayr.trackers import Deleted, ItemDraft, ItemFields, ItemRef
from relayr.trackers.events import (
    ItemChanged,
    ItemCommented,
    ItemCreated,
    ItemRemoved,
    TrackerEvent,
)
from tests.clock import FakeClock
from tests.trackers.conftest import KEY, PROJECT
from tests.trackers.following import Following, following

PEOPLES: dict[str, tuple[str, ...]] = {
    "state": ("backlog", "todo", "started"),
    "priority": ("none", "low", "high"),
}
RELAYRS: dict[str, tuple[str, ...]] = {"state": ("done", "cancelled"), "priority": ("urgent",)}
POISON = "high"
"""A value whose change's projection raises."""

FIELDS = st.sampled_from(sorted(PEOPLES))
DAY = timedelta(days=1)


def project(event: TrackerEvent) -> reflexr.Event | None:
    if isinstance(event, ItemChanged) and event.new == POISON:
        raise ValueError("poisoned")
    return event


class Reading(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.clock = FakeClock()
        self.app: Following = following(
            InMemoryLedger(clock=self.clock), self.clock, budget=100_000, projections={KEY: project}
        )
        self.filed: dict[str, ItemRef] = {}
        """The items lattice filed, by their ids."""

        self.writers: dict[tuple[str, str], str] = {}
        """Who changed each item's field last: `person` or `relayr`."""

        self.seen: dict[str, dict[str, JsonValue]] | None = None
        """Each item as the last poll found it; None before the first."""

        self.replies: set[str] = set()
        """The comments people posted since the last poll."""

        self.swept = self.clock.now
        self.published = 0
        self.letters = 0

    def teardown(self) -> None:
        self.loop.close()

    def run[T](self, command: Coroutine[Any, Any, T]) -> T:
        return self.loop.run_until_complete(command)

    def written(self, command: Coroutine[Any, Any, None]) -> bool:
        """Make a run's write; False if the cap on loops refused it."""
        try:
            self.run(command)
        except RunFailure as failure:
            refused = failure.reason
        else:
            return True
        assert refused == "tracker_loop"
        return False

    def items(self) -> dict[str, dict[str, JsonValue]]:
        return {
            item.ref.id: item.model_dump(mode="json") for item in self.app.tracker.items_in(PROJECT)
        }

    def act(self) -> None:
        """Each change is a second after the one before, as people and runs make them."""
        self.clock.advance(timedelta(seconds=1))

    # ─── what people and runs do ──────────────────────────────────────────────

    @rule(title=st.sampled_from(["P-a", "P-b"]))
    def add(self, title: str) -> None:
        self.act()
        self.app.tracker.add(PROJECT, title)

    @rule(key=st.sampled_from(["a", "b"]))
    def file(self, key: str) -> None:
        self.act()

        async def filed() -> ItemRef | Deleted:
            return await (await self.app.acting()).ensure_item(ItemDraft(title="R"), key=key)

        made = self.run(filed())
        if isinstance(made, ItemRef):
            self.filed[made.id] = made

    @precondition(lambda self: self.items())
    @rule(data=st.data(), name=FIELDS)
    def person_edits(self, data: st.DataObject, name: str) -> None:
        self.act()
        item_id = data.draw(st.sampled_from(sorted(self.items())))
        value = data.draw(st.sampled_from(PEOPLES[name]))
        ref = ItemRef(project=PROJECT, id=item_id, number=0, name="")
        self.app.tracker.edit(ref, ItemFields.model_validate({name: value}))
        self.writers[item_id, name] = "person"

    @precondition(lambda self: self.filed.keys() & self.items().keys())
    @rule(data=st.data(), name=FIELDS)
    def run_edits(self, data: st.DataObject, name: str) -> None:
        self.act()
        item_id = data.draw(st.sampled_from(sorted(self.filed.keys() & self.items().keys())))
        value = data.draw(st.sampled_from(RELAYRS[name]))

        async def edit() -> None:
            fields = ItemFields.model_validate({name: value})
            await (await self.app.acting()).update(self.filed[item_id], fields)

        held = self.items()[item_id][name]
        if self.written(edit()) and held != value:
            self.writers[item_id, name] = "relayr"

    @precondition(lambda self: self.items())
    @rule(data=st.data(), ours=st.booleans())
    def comment(self, data: st.DataObject, ours: bool) -> None:
        self.act()
        item_id = data.draw(st.sampled_from(sorted(self.items())))
        ref = ItemRef(project=PROJECT, id=item_id, number=0, name="")
        if not ours:
            self.replies.add(self.app.tracker.reply(ref, "<p>A person's.</p>").id)
            return

        async def comment() -> None:
            await (await self.app.acting()).comment(ref, "<p>relayr's.</p>")

        self.written(comment())

    @precondition(lambda self: self.items())
    @rule(data=st.data())
    def delete(self, data: st.DataObject) -> None:
        self.act()
        item_id = data.draw(st.sampled_from(sorted(self.items())))
        self.app.tracker.delete(ItemRef(project=PROJECT, id=item_id, number=0, name=""))
        self.replies = {r for r in self.replies if not r.startswith(f"{item_id}-")}

    @rule()
    def a_day_passes(self) -> None:
        self.clock.advance(DAY)

    # ─── what the follower publishes ──────────────────────────────────────────

    @rule()
    def poll(self) -> None:
        sweeping = self.seen is None or self.clock.now - self.swept >= DAY
        assert self.run(self.app.poll())
        events = self.run(self.app.events())
        new, self.published = events[self.published :], len(events)
        letters = self.run(self.app.ledger.tracker_dead_letters(KEY))
        dead, self.letters = len(letters) - self.letters, len(letters)
        assert len({letter.event_id for letter in letters}) == len(letters), "once per id"
        now = self.items()
        if self.seen is None:
            assert new == [], "a new binding publishes nothing"
        else:
            self.check(new, now, dead, sweeping=sweeping)
        if sweeping:
            self.swept = self.clock.now
        self.seen = now if sweeping or self.seen is None else {**self.seen, **now}
        self.replies = set()
        assert self.run(self.app.poll())
        assert len(self.run(self.app.events())) == self.published, "read again: nothing new"

    def check(
        self,
        new: list[TrackerEvent],
        now: dict[str, dict[str, JsonValue]],
        dead: int,
        *,
        sweeping: bool,
    ) -> None:
        assert self.seen is not None
        expected: set[tuple[str, str, JsonValue]] = set()
        for item_id, item in now.items():
            before = self.seen.get(item_id)
            if before is None:
                continue
            for name in PEOPLES:
                if item[name] != before[name] and self.writers.get((item_id, name)) == "person":
                    expected.add((item_id, name, item[name]))
        poisoned = {change for change in expected if change[2] == POISON}
        changed = {(e.item_id, e.field, e.new) for e in new if isinstance(e, ItemChanged)}
        assert changed == expected - poisoned, "every person's change, and none of relayr's"
        assert dead == len(poisoned), "each poisoned change dead-lettered"
        created = {e.item_id for e in new if isinstance(e, ItemCreated)}
        assert created == (now.keys() - self.seen.keys()) - self.filed.keys()
        commented = [e.model_dump()["comment_id"] for e in new if isinstance(e, ItemCommented)]
        assert sorted(commented) == sorted(self.replies), "people's comments, once, not relayr's"
        removed = {e.item_id for e in new if isinstance(e, ItemRemoved)}
        assert removed == ((self.seen.keys() - now.keys()) if sweeping else set())


Reading.TestCase.settings = settings(max_examples=100, stateful_step_count=30, deadline=None)
TestReading = Reading.TestCase
