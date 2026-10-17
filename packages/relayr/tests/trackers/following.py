"""A bound workspace whose fake tracker a follower reads, and what the follower published."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from opentelemetry.metrics import MeterProvider

import reflexr
import reflexr.workspace as r
from reflexr.core import Envelope
from relayr.integrations import Enabled, always
from relayr.ledger import Ledger, WorkspaceKey
from relayr.outbound import Allowlist
from relayr.trackers import (
    FakeTracker,
    ItemDraft,
    ItemRef,
    TrackerActions,
    TrackerBinding,
    TrackerFollowers,
    Trackers,
)
from relayr.trackers.events import PUBLISHERS, TRACKED, TrackerEvent, TrackerProjection
from tests.app_types import Deployed
from tests.clock import FakeClock
from tests.trackers.conftest import ALLOWED, BINDING, FILE, KEY, Tenant

type Rules = Sequence[reflexr.Rule]


@dataclass
class Following:
    """A process's followers of the bound workspace, its runs, and the workspace they publish to."""

    tracker: FakeTracker
    ledger: Ledger
    clock: FakeClock
    tenant: Tenant
    storage: r.InMemoryStorage
    """reflexr's storage, which another process may share."""

    workspaces: r.Workspaces
    trackers: Trackers
    followers: TrackerFollowers
    actions: Mapping[str, r.Action[Trackers]]
    reactions: int = field(default=0)

    def reactor(self) -> r.Reactor[Trackers]:
        """A reactor that runs the rules' actions, with the connector as their dependency."""
        return r.Reactor(self.workspaces, actions=self.actions, deps=self.trackers)

    async def poll(self, workspace: WorkspaceKey = KEY) -> bool:
        return await self.followers.poll(*workspace)

    async def published(self, workspace: WorkspaceKey = KEY) -> list[Envelope]:
        """What the followers published into a workspace, oldest first."""
        handle = await self.workspaces.open(*workspace, actor=reflexr.SystemActor())
        return [e for e in await handle.read() if e.event.event_namespace != "reflexr"]

    async def events(self, workspace: WorkspaceKey = KEY) -> list[TrackerEvent]:
        return [
            e.event for e in await self.published(workspace) if isinstance(e.event, TrackerEvent)
        ]

    async def acting(self, workspace: WorkspaceKey = KEY) -> TrackerActions:
        """What a new run of the rule may do in the workspace's tracker."""
        self.reactions += 1
        handle = await self.workspaces.open(*workspace, actor=reflexr.SourceActor(name="ci"))
        await handle.publish(Deployed(service=f"svc-{self.reactions}"))
        await self.reactor().evaluate()
        run = max(await handle.runs(), key=lambda run: run.fired_seq)
        reaction = r.Reaction(workspace=handle, run=run, rule=FILE, events=(), deps=self.trackers)
        return self.trackers.acting(reaction)

    async def filed(self, key: str, title: str = "A run failed") -> ItemRef:
        item = await (await self.acting()).ensure_item(ItemDraft(title=title), key=key)
        assert isinstance(item, ItemRef)
        return item


async def _idle(reaction: r.Reaction[Trackers]) -> None:
    """The rule's action, which these tests never run: they act through its reactions."""


def following(
    ledger: Ledger,
    clock: FakeClock,
    *,
    tracker: FakeTracker | None = None,
    bindings: Mapping[WorkspaceKey, TrackerBinding] | None = None,
    enabled: Enabled = always,
    budget: int = 40,
    projections: Mapping[WorkspaceKey, TrackerProjection] | None = None,
    rules: Rules = (),
    actions: Mapping[str, r.Action[Trackers]] | None = None,
    events: Sequence[type[reflexr.Event]] = (),
    holder: str = "p1",
    allowlists: Mapping[str, Allowlist] = ALLOWED,
    tenant: Tenant | None = None,
    storage: r.InMemoryStorage | None = None,
    max_depth: int = 8,
    interval: timedelta = timedelta(seconds=30),
    lease_ttl: timedelta = timedelta(seconds=30),
    meter_provider: MeterProvider | None = None,
) -> Following:
    """A process that follows the bound workspace, its storage shared if given."""
    tracker = tracker or FakeTracker(clock=clock)
    tenant = tenant or Tenant()
    storage = storage or r.InMemoryStorage(clock=clock)
    workspaces = r.Workspaces(
        storage,
        events=(Deployed, *TRACKED, *events),
        rules=[FILE, *rules],
        publishers=PUBLISHERS,
        clock=clock,
        max_depth=max_depth,
    )
    trackers = Trackers(
        ledger,
        connect=tracker.connect,
        credentials=tenant,
        bindings={KEY: BINDING} if bindings is None else bindings,
        allowlists=allowlists,
        integration="tracker:fake",
        enabled=enabled,
        budget=budget,
        clock=clock,
    )
    followers = TrackerFollowers(
        trackers,
        workspaces,
        projections=projections,
        holder=holder,
        interval=interval,
        lease_ttl=lease_ttl,
        clock=clock,
        meter_provider=meter_provider,
    )
    every = {"file": _idle, **(actions or {})}
    return Following(
        tracker, ledger, clock, tenant, storage, workspaces, trackers, followers, every
    )


def changes(events: Sequence[TrackerEvent]) -> list[tuple[Any, ...]]:
    """Each event, as what it says changed: its type, its item, and its field and new value."""
    found: list[tuple[Any, ...]] = []
    for event in events:
        said = event.model_dump()
        match event.event_type:
            case "tracker:item_changed":
                found.append(("changed", event.item_id, said["field"], said["new"]))
            case "tracker:item_commented":
                found.append(("commented", event.item_id, said["body"]))
            case "tracker:item_removed":
                found.append(("removed", event.item_id, said["deleted"]))
            case _:
                found.append(("created", event.item_id, said["title"]))
    return found


class Elsewhere(reflexr.Event, abstract=True, event_namespace="elsewhere"):
    """A namespace reflexr's workspaces here don't accept."""


class Odd(Elsewhere, name="odd"):
    """An event a projection may return, which reflexr refuses."""
