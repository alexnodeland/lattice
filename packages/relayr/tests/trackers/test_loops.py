"""Loops through a tracker (lattice RFC-0004, decision T7): the echo filter ends them, and the cap
on writes to one item ends what the filter can't see.

Phase 2's exit criterion: two rules that answer each other through the tracker make no loop, and
stop at the write cap with the echo filter turned off.
"""

from collections.abc import Mapping
from datetime import timedelta

from pydantic import BaseModel, JsonValue

import reflexr
import reflexr.workspace as r
from reflexr.core import RunDeadLettered
from relayr.ledger import InMemoryLedger, Ledger, WorkspaceKey
from relayr.outbound import Allowlist
from relayr.trackers import LOOP_CAP, ItemFields, ItemRef, State, Trackers
from relayr.trackers.events import ItemChanged
from tests.clock import FakeClock
from tests.trackers.conftest import KEY
from tests.trackers.following import Following, following

ALLOWED = {"ops:*": Allowlist(trackers=True)}
BUDGET = 1000
"""Enough that every poll reads: here the rules run a second apart, not a minute."""


class Unrecorded(InMemoryLedger):
    """A ledger that records none of the values relayr writes: the echo filter turned off."""

    async def record_written(
        self, workspace: WorkspaceKey, key: str, fields: Mapping[str, JsonValue]
    ) -> None:
        return None


class To(BaseModel):
    to: State


def answering(name: str, heard: State, says: State) -> reflexr.Rule:
    """A rule that, when an item's state becomes one, moves it to another."""
    return reflexr.Rule(
        name=f"ops:{name}",
        when=reflexr.on(ItemChanged).where(field="state", new=heard),
        then=reflexr.run("move", to=says),
    )


RULES = (answering("reopen", "done", "todo"), answering("close", "todo", "done"))


async def move(reaction: r.Reaction[Trackers], params: To) -> None:
    event = reaction.events[0].event
    assert isinstance(event, ItemChanged)
    item = ItemRef(
        project=event.project, id=event.item_id, number=event.number, name=event.name, key=event.key
    )
    await reaction.deps.acting(reaction).set_state(item, params.to)


ACTIONS = {"move": r.with_params(move, To)}


async def answered(app: Following) -> list[tuple[str, JsonValue]]:
    """Poll and run the rules, a second apart, until neither has anything to do; return the
    changes the follower published."""
    reactor = app.reactor()
    while True:
        before = len(await app.events())
        await app.poll()
        settled = await reactor.settle()
        app.clock.advance(timedelta(seconds=1))
        if not settled.attempts and len(await app.events()) == before:
            return [(e.field, e.new) for e in await app.events() if isinstance(e, ItemChanged)]


async def test_two_rules_answering_each_other_make_no_loop(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock, rules=RULES, actions=ACTIONS, allowlists=ALLOWED, budget=BUDGET)
    item = await app.filed("incident/1")
    assert await app.poll()
    app.tracker.edit(item, ItemFields(state="done"), by="ada")
    assert await answered(app) == [("state", "done")], "the rule's write is an echo"
    [after] = app.tracker.items_in("ops")
    assert after.state == "todo"


async def test_with_the_echo_filter_off_they_stop_at_the_cap(clock: FakeClock) -> None:
    app = following(
        Unrecorded(clock=clock),
        clock,
        rules=RULES,
        actions=ACTIONS,
        allowlists=ALLOWED,
        budget=BUDGET,
    )
    item = await app.filed("incident/1")
    assert await app.poll()
    app.tracker.edit(item, ItemFields(state="done"), by="ada")
    changes = await answered(app)
    assert len(changes) == 1 + LOOP_CAP, "a person's change, then each write the cap let through"
    handle = await app.workspaces.open(*KEY, actor=reflexr.SystemActor())
    [failed] = [e.event for e in await handle.read() if isinstance(e.event, RunDeadLettered)]
    assert failed.reason == "tracker_loop"
