"""The followers as tasks: started on open and at startup, woken by nudges, held by a lease, and
idle where their integration is off."""

import asyncio
import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint

from relayr.ledger import Ledger, WorkspaceKey
from relayr.telemetry import FOLLOWERS_STOPPED, NUDGES_REFUSED, UNNUDGED
from relayr.trackers import ItemFields, RateLimited, TrackerBinding, followers
from relayr.trackers.fake import SIGNATURE
from tests.clock import FakeClock
from tests.stack import until
from tests.trackers.conftest import BINDING, KEY, PROJECT, TENANT
from tests.trackers.following import Following, Odd, changes, following

QUICK = timedelta(milliseconds=10)
"""An interval for tests that wait for polls."""

LONG = timedelta(minutes=10)
"""An interval for tests that poll only when nudged."""

TTL = timedelta(milliseconds=30)


@pytest.fixture
def reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


def counted(reader: InMemoryMetricReader, name: str) -> list[tuple[dict[str, Any], int]]:
    """A counter's points: their attributes, and their values."""
    data = reader.get_metrics_data()
    return [
        (dict(point.attributes or {}), int(point.value))
        for resource in (data.resource_metrics if data else ())
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
        for point in metric.data.data_points
        if isinstance(point, NumberDataPoint)
    ]


def nudge(project: str = PROJECT, secret: str = "secret") -> tuple[dict[str, str], bytes]:
    body = json.dumps({"project": project}).encode()
    return {SIGNATURE: hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}, body


async def published(app: Following, count: int) -> None:
    async def enough() -> bool:
        return len(await app.events()) >= count

    await until(enough)


async def test_a_follower_starts_on_open_and_polls_every_interval(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock, interval=QUICK, lease_ttl=TTL)
    await app.followers.watch(TENANT, "dev")  # unbound: left alone
    await app.followers.watch(*KEY)
    await app.followers.watch(*KEY)  # followed already
    await until(lambda: _seeded(ledger))
    item = app.tracker.add(PROJECT, "Filed")
    await published(app, 1)
    app.tracker.edit(item, ItemFields(title="Renamed"))
    await published(app, 2)
    await app.followers.aclose()
    await app.followers.watch(*KEY)  # closed: starts nothing
    assert changes(await app.events()) == [
        ("created", item.id, "Filed"),
        ("changed", item.id, "title", "Renamed"),
    ]
    assert await ledger.acquire_tracker_lease(KEY, "p2", timedelta(seconds=1)), "released"


async def _seeded(ledger: Ledger) -> bool:
    return await ledger.tracker_following(KEY) is not None


async def test_resume_follows_every_bound_workspace(ledger: Ledger, clock: FakeClock) -> None:
    dev = WorkspaceKey(TENANT, "dev")
    app = following(
        ledger, clock, bindings={KEY: BINDING, dev: BINDING}, interval=QUICK, lease_ttl=TTL
    )
    await app.followers.resume()

    async def both() -> bool:
        return all([await ledger.tracker_following(w) is not None for w in (KEY, dev)])

    await until(both)
    await app.followers.aclose()


async def test_a_nudge_wakes_the_follower_that_holds_the_lease(
    ledger: Ledger, clock: FakeClock, reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(followers, "DEBOUNCE", timedelta(milliseconds=10))
    app = following(
        ledger,
        clock,
        meter_provider=MeterProvider(metric_readers=[reader]),
        interval=LONG,
        lease_ttl=TTL,
    )
    await app.followers.watch(*KEY)
    await until(lambda: _seeded(ledger))
    item = app.tracker.add(PROJECT, "Filed")
    assert await app.followers.nudge(TENANT, "fake", *nudge())
    await published(app, 1)
    assert await app.followers.nudge(TENANT, "fake", *nudge("dev")), "another project: no poll"
    app.tracker.edit(item, ItemFields(title="Renamed"))
    await asyncio.sleep(0.05)
    assert len(await app.events()) == 1
    assert counted(reader, UNNUDGED.name) == [], "what a nudge announced is not unnudged"
    await app.followers.aclose()


async def test_a_nudge_that_doesnt_verify_is_refused_and_counted(
    ledger: Ledger, clock: FakeClock, reader: InMemoryMetricReader
) -> None:
    app = following(
        ledger,
        clock,
        meter_provider=MeterProvider(metric_readers=[reader]),
        interval=LONG,
        lease_ttl=TTL,
    )
    assert not await app.followers.nudge(TENANT, "fake", *nudge()), "no credentials read yet"
    assert app.tenant.asked == [], "a nudge never asks for them"
    assert await app.poll()
    assert await app.followers.nudge(TENANT, "fake", *nudge()), "verified; no follower to wake"
    assert not await app.followers.nudge(TENANT, "fake", *nudge(secret="forged"))
    assert not await app.followers.nudge(TENANT, "plane", *nudge()), "another tracker's route"
    assert not await app.followers.nudge("globex", "fake", *nudge()), "an unknown tenant"
    headers, _ = nudge()
    assert not await app.followers.nudge(TENANT, "fake", headers, b"not json")
    assert counted(reader, NUDGES_REFUSED.name) == [({}, 5)]


async def test_a_change_no_nudge_announced_is_counted(
    ledger: Ledger, clock: FakeClock, reader: InMemoryMetricReader
) -> None:
    app = following(ledger, clock, meter_provider=MeterProvider(metric_readers=[reader]))
    assert await app.poll()
    app.tracker.add(PROJECT, "One")
    app.tracker.add(PROJECT, "Two")
    assert await app.poll()
    assert counted(reader, UNNUDGED.name) == [({**_tenancy()}, 2)]


def _tenancy() -> dict[str, str]:
    return {"relayr.tenant.id": TENANT, "relayr.workspace.id": KEY.workspace_id}


async def test_a_switched_off_follower_lets_its_lease_go_until_it_is_on(
    ledger: Ledger, clock: FakeClock
) -> None:
    switched = {"on": True}

    async def enabled(tenant_id: str, workspace_id: str, key: str, /) -> bool:
        return switched["on"]

    app = following(ledger, clock, enabled=enabled, interval=QUICK, lease_ttl=TTL)
    await app.followers.watch(*KEY)
    await until(lambda: _seeded(ledger))
    switched["on"] = False

    async def released() -> bool:
        taken = await ledger.acquire_tracker_lease(KEY, "p2", timedelta(milliseconds=1))
        if taken:
            await ledger.release_tracker_lease(KEY, "p2")
        return taken

    await until(released)
    app.tracker.add(PROJECT, "Filed while off")
    await asyncio.sleep(0.05)
    assert await app.events() == []
    switched["on"] = True
    await published(app, 1)
    await app.followers.aclose()


async def test_a_follower_another_process_holds_waits_for_its_lease(
    ledger: Ledger, clock: FakeClock
) -> None:
    holder = following(ledger, clock, holder="p2")
    assert await holder.poll()
    app = following(
        ledger, clock, tracker=holder.tracker, storage=holder.storage, interval=QUICK, lease_ttl=TTL
    )
    await app.followers.watch(*KEY)
    app.tracker.add(PROJECT, "Filed")
    await asyncio.sleep(0.05)
    assert await app.events() == [], "p2 holds the lease"
    clock.advance(timedelta(minutes=1))
    await published(app, 1)
    await app.followers.aclose()


async def test_a_rate_limited_follower_waits_as_the_tracker_asks(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock, interval=QUICK, lease_ttl=TTL)
    app.tracker.fail(RateLimited(0.05))
    loop = asyncio.get_running_loop()
    began = loop.time()
    await app.followers.watch(*KEY)
    await until(lambda: _seeded(ledger))
    assert loop.time() - began >= 0.05
    await app.followers.aclose()


async def test_a_rate_limit_that_names_no_wait_waits_an_interval(
    ledger: Ledger, clock: FakeClock
) -> None:
    app = following(ledger, clock, interval=QUICK, lease_ttl=TTL)
    app.tracker.fail(RateLimited(None))
    await app.followers.watch(*KEY)
    await until(lambda: _seeded(ledger))
    await app.followers.aclose()


async def test_a_follower_that_meets_anything_else_stops_and_is_counted(
    ledger: Ledger, clock: FakeClock, reader: InMemoryMetricReader
) -> None:
    meter = MeterProvider(metric_readers=[reader])
    app = following(
        ledger,
        clock,
        projections={KEY: lambda event: Odd()},
        meter_provider=meter,
        interval=QUICK,
        lease_ttl=TTL,
    )
    await app.followers.watch(*KEY)
    await until(lambda: _seeded(ledger))
    app.tracker.add(PROJECT, "Filed")

    async def stopped() -> bool:
        return bool(counted(reader, FOLLOWERS_STOPPED.name))

    await until(stopped)
    [(attributes, count)] = counted(reader, FOLLOWERS_STOPPED.name)
    assert (attributes["error.type"], count) == ("NotFound", 1)
    await app.followers.watch(*KEY)  # started again on the next open
    await app.followers.aclose()


async def test_projects_bound_in_other_workspaces_are_woken_alike(
    ledger: Ledger, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(followers, "DEBOUNCE", timedelta(milliseconds=10))
    dev = WorkspaceKey(TENANT, "dev")
    bindings = {KEY: BINDING, dev: TrackerBinding(project=PROJECT)}
    app = following(ledger, clock, bindings=bindings, interval=LONG, lease_ttl=TTL)
    await app.followers.resume()

    async def both() -> bool:
        return all([await ledger.tracker_following(w) is not None for w in (KEY, dev)])

    await until(both)
    app.tracker.add(PROJECT, "Filed")
    assert await app.followers.nudge(TENANT, "fake", *nudge())

    async def in_both() -> bool:
        return bool(await app.events()) and bool(await app.events(dev))

    await until(in_both)
    await app.followers.aclose()
