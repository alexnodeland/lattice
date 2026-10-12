"""A draft's preview replays the recent log through the rule, and runs nothing."""

from datetime import timedelta

import pytest

import reflexr
import reflexr.workspace as r
from relayr.rules import Preview, preview
from tests.app_types import Deployed
from tests.clock import START, FakeClock

RULE = reflexr.Rule(
    name="chat:deploys",
    when=reflexr.on(Deployed).where(reflexr.F.service.eq("auth")),
    then=reflexr.run("notify"),
)


async def _workspace(clock: FakeClock, services: list[str]) -> r.Workspace:
    """A workspace whose log has a deploy of each service, an hour apart."""
    workspaces = r.Workspaces(r.InMemoryStorage(clock=clock), events=[Deployed])
    workspace = await workspaces.open("acme", "prod", actor=reflexr.SystemActor())
    for service in services:
        await workspace.publish(Deployed(service=service))
        clock.advance(timedelta(hours=1))
    return workspace


async def test_it_counts_what_would_have_fired_in_the_window(clock: FakeClock) -> None:
    workspace = await _workspace(clock, ["auth", "auth", "billing", "auth"])
    since = START + timedelta(minutes=30)
    head = len(await workspace.read())
    previewed = await preview(workspace, RULE, since=since)
    assert previewed == Preview(firings=2, replayed=3, since=since, complete=True)
    assert len(await workspace.read()) == head, "it writes nothing"
    assert await workspace.runs() == [], "and runs nothing"


async def test_it_replays_only_the_newest_envelopes_past_its_limit(clock: FakeClock) -> None:
    workspace = await _workspace(clock, ["auth"] * 5)
    previewed = await preview(workspace, RULE, since=START, limit=2)
    assert (previewed.firings, previewed.replayed, previewed.complete) == (2, 2, False)


@pytest.mark.parametrize("services", [[], ["auth"]])
async def test_an_empty_window_fires_nothing(clock: FakeClock, services: list[str]) -> None:
    workspace = await _workspace(clock, services)
    previewed = await preview(workspace, RULE, since=clock.now)
    assert (previewed.firings, previewed.replayed, previewed.complete) == (0, 0, True)
