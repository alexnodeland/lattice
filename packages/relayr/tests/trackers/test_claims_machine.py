"""Filing once, as a state machine: runs file by keys while the tracker loses answers and fails,
time passes, and people delete and archive what was filed.

Whatever the order, the invariants of lattice RFC-0004's "Writing once" hold: a key files at most
one item, however its writes were lost and retried; an item a person deleted is never filed
again, and once a run is told so, every run is; and what the ledger recorded for a key is the
item the key filed.
"""

import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

import reflexr
import reflexr.workspace as r
from reflexr.workspace import RunFailure
from relayr.ledger import InMemoryLedger
from relayr.trackers import Deleted, FakeTracker, ItemDraft, ItemRef, Unavailable
from tests.app_types import Deployed
from tests.clock import FakeClock
from tests.trackers.conftest import FILE, KEY, PROJECT, Runs, Tenant, connector

KEYS = st.sampled_from(["a", "b", "c"])


class Filing(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.clock = FakeClock()
        self.ledger = InMemoryLedger(clock=self.clock)
        self.tracker = FakeTracker(clock=self.clock)
        self.filed: dict[str, ItemRef] = {}
        """Each key's item, as a run was given it."""

        self.gone: set[str] = set()
        """The keys whose item a person deleted."""

        self.dead: set[str] = set()
        """The keys a run was told their item was deleted."""

        try:
            self.runs = self.run(self.open())
        except BaseException:
            self.loop.close()
            raise

    async def open(self) -> Runs:
        workspaces = r.Workspaces(
            r.InMemoryStorage(clock=self.clock), events=(Deployed,), rules=[FILE], clock=self.clock
        )
        workspace = await workspaces.open(*KEY, actor=reflexr.SourceActor(name="ci"))
        trackers = connector(self.ledger, self.tracker, Tenant(), self.clock)
        return Runs(workspaces, workspace, trackers)

    def teardown(self) -> None:
        self.loop.close()

    def run[T](self, command: Coroutine[Any, Any, T]) -> T:
        return self.loop.run_until_complete(command)

    @rule(key=KEYS, lost=st.booleans(), fails=st.booleans())
    def file(self, key: str, lost: bool, fails: bool) -> None:
        """A run files by a key, its answer lost or its request failed if so drawn."""
        if lost:
            self.tracker.lose_next_created()
        if fails:
            self.tracker.fail(Unavailable("down"))

        async def file() -> ItemRef | Deleted | str:
            acting = self.runs.trackers.acting(await self.runs.reaction())
            try:
                return await acting.ensure_item(ItemDraft(title=key), key=key)
            except RunFailure as failure:
                return failure.reason

        told = key in self.dead
        match self.run(file()):
            case Deleted():
                assert key in self.gone
                self.dead.add(key)
            case ItemRef() as ref:
                assert key not in self.gone, "a deleted item is never filed again"
                assert self.filed.setdefault(key, ref) == ref, "a key files one item"
            case reason:
                assert not told, "once a run is told an item was deleted, every run is"
                assert reason in ("tracker_unavailable", "tracker_claimed"), "retried later"

    @rule(seconds=st.integers(min_value=0, max_value=40))
    def wait(self, seconds: int) -> None:
        self.clock.advance(timedelta(seconds=seconds))

    @precondition(lambda self: self.filed.keys() - self.gone)
    @rule(data=st.data())
    def delete(self, data: st.DataObject) -> None:
        """A person deletes an item a run was given."""
        key = data.draw(st.sampled_from(sorted(self.filed.keys() - self.gone)))
        if self.filed[key].id in self.ids():
            self.tracker.delete(self.filed[key])
            self.gone.add(key)

    @precondition(lambda self: self.filed)
    @rule(data=st.data())
    def archive(self, data: st.DataObject) -> None:
        """A person archives an item: it is still filed."""
        key = data.draw(st.sampled_from(sorted(self.filed)))
        if self.filed[key].id in self.ids():
            self.tracker.archive(self.filed[key])

    def ids(self) -> set[str]:
        return {item.ref.id for item in self.tracker.items_in(PROJECT)}

    @invariant()
    def a_key_filed_at_most_one_item(self) -> None:
        claimed = {k for k in ("a", "b", "c") if self.run(self.ledger.tracked(KEY, "item", k))}
        assert self.tracker.created <= len(claimed), "every item filed was a key's, once"

    @invariant()
    def the_ledger_records_the_item_a_key_filed(self) -> None:
        for key, ref in self.filed.items():
            tracked = self.run(self.ledger.tracked(KEY, "item", key))
            assert tracked is not None
            assert tracked.ref == ref.model_dump(mode="json")


Filing.TestCase.settings = settings(max_examples=100, stateful_step_count=25, deadline=None)
TestFiling = Filing.TestCase
