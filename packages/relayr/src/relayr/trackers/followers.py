"""Tracker followers: one per bound workspace, publishing what people change in its project.

A follower holds its workspace's tracker lease in the ledger, so one process at a time reads the
project, and polls it every interval, sooner when a webhook nudges it. Each poll reads the items
changed since two minutes before its cursor, compares each with the snapshot the ledger keeps
of it, and publishes one `tracker:` event per field that differs, and one per new comment; then
it saves the snapshots, and only then moves its cursor. Every event's id is derived from what it
says, so a page read again, by another process or after a restart, publishes nothing new.

Once a day, and when a binding is first read, it reads the whole project: an item no longer
listed is published as removed, and an item no poll saw change is compared all the same. A new
binding's first read publishes nothing, unless it names a `since`.

relayr's own writes are dropped by value: a field whose new value is the one relayr recorded
before writing it, an item whose creation lattice claimed, and a comment lattice posted. What
remains is a person's. A person's change to an item a run filed joins that run's chain, without
causation, so depth never grows through a tracker; the cap on writes to one item ends a loop the
filter can't see.

A follower does nothing in a workspace where its integration is off, and stops on anything but a
tracker's failure, until its workspace is next opened.
"""

import asyncio
import contextlib
import hashlib
import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, TypedDict, get_args

from opentelemetry import context as otel_context
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import TracerProvider
from pydantic import JsonValue

import reflexr.workspace
from reflexr import new_id
from reflexr.core import Forbidden, NotFound
from relayr.ledger import (
    Clock,
    Ledger,
    Snapshot,
    TrackerDeadLetter,
    TrackerFollowing,
    WorkspaceKey,
    utc_now,
)
from relayr.outbound.ids import canonical
from relayr.telemetry import (
    ERROR_TYPE,
    EVENT_TYPE,
    FOLLOWERS_STOPPED,
    NUDGES_REFUSED,
    TRACKER_DEAD_LETTERS,
    UNNUDGED,
    Telemetry,
    workspace_attributes,
)
from relayr.trackers.actions import TrackerBinding, Trackers
from relayr.trackers.budget import Budget
from relayr.trackers.events import (
    SOURCE,
    Field,
    ItemChanged,
    ItemCommented,
    ItemCreated,
    ItemRemoved,
    TrackerEvent,
    TrackerProjection,
)
from relayr.trackers.port import Cursor, Item, RateLimited, Tracker, TrackerError, Unauthorized

logger = logging.getLogger("relayr.trackers")

LOOK_BACK: Final = timedelta(minutes=2)
"""How far before its cursor a poll reads: a change can commit with an `updated_at` older than
one already read."""

DEBOUNCE: Final = timedelta(seconds=2)
"""How soon after a poll began a nudge makes another."""

FIELDS: Final[tuple[Field, ...]] = get_args(Field.__value__)
"""The fields of an item a change is read on."""


def event_id(*parts: str) -> str:
    """The id of a `tracker:` event: `trk_` and 16 hex digits of a digest of what it says."""
    return f"trk_{hashlib.sha256('\x00'.join(parts).encode()).hexdigest()[:16]}"


class TrackerFollowers:
    """Follows the tracker project each bound workspace reads, from when it is first opened.

    Give [`watch`][relayr.trackers.TrackerFollowers.watch] to reflexr's `Workspaces` as its
    `on_open`, composed with any other, and call
    [`resume`][relayr.trackers.TrackerFollowers.resume] at startup, so every bound project is
    read whether or not its workspace is opened.

    Args:
        trackers: The connector: its bindings, credentials, budget and integration switch.
        reflexr: The workspaces the events are published into. Their `events` must include
            [`TRACKED`][relayr.trackers.events.TRACKED] and the types the projections return,
            and their `publishers` should reserve the namespace with
            [`PUBLISHERS`][relayr.trackers.events.PUBLISHERS].
        projections: What a bound workspace's events become, in place of the `tracker:` events
            themselves.
        holder: This process's name in leases. Defaults to a new random id.
        lease_ttl: How long a lease lasts unless renewed; it is renewed every third of that.
        interval: How long a follower waits between polls, unless a webhook nudges it.
        sweep_every: How often a follower reads the whole project.
        clock: Returns the current time, which sweeps are due by.
        tracer_provider: Where the polls' spans go. Defaults to the global provider.
        meter_provider: Where the counters go. Defaults to the global provider.
    """

    def __init__(
        self,
        trackers: Trackers,
        reflexr: reflexr.workspace.Workspaces,
        *,
        projections: Mapping[WorkspaceKey, TrackerProjection] | None = None,
        holder: str | None = None,
        lease_ttl: timedelta = timedelta(seconds=30),
        interval: timedelta = timedelta(seconds=30),
        sweep_every: timedelta = timedelta(days=1),
        clock: Clock = utc_now,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self._trackers = trackers
        self._ledger = trackers.ledger
        self._reflexr = reflexr
        self._projections = dict(projections or {})
        self._holder = holder or new_id("relayr")
        self._ttl = lease_ttl
        self._interval = interval
        self._sweep_every = sweep_every
        self._clock = clock
        self._telemetry = Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider)
        self._tracker = trackers.integration.removeprefix("tracker:")
        self._tasks: dict[WorkspaceKey, asyncio.Task[None]] = {}
        self._held: dict[WorkspaceKey, asyncio.Event] = {}
        self._refused: set[WorkspaceKey] = set()
        self._closed = False

    async def watch(self, tenant_id: str, workspace_id: str) -> None:
        """Follow a bound workspace's project, unless it is followed already: the `on_open` hook.

        A workspace with no binding is left alone.
        """
        workspace = WorkspaceKey(tenant_id, workspace_id)
        if self._closed or workspace in self._tasks or workspace not in self._trackers.bindings:
            return
        task = asyncio.create_task(self._follow(workspace))
        self._tasks[workspace] = task
        task.add_done_callback(lambda done: self._ended(workspace, done))

    async def resume(self) -> None:
        """Follow every bound workspace's project: call it when the application starts."""
        for workspace in self._trackers.bindings:
            await self.watch(*workspace)

    async def poll(self, tenant_id: str, workspace_id: str) -> bool:
        """Read a bound workspace's project once, now, as its follower does each interval.

        It takes the workspace's lease, and leaves it held until it lapses. Returns whether it
        read: not if the workspace is unbound, its integration is off, or another process holds
        its lease. A tracker's failure is logged, and read past.
        """
        workspace = WorkspaceKey(tenant_id, workspace_id)
        if workspace not in self._trackers.bindings or not await self._may(workspace):
            return False
        target = await self._reflexr.open(*workspace, actor=SOURCE)
        await self._poll(workspace, target, nudged=False)
        return True

    async def nudge(
        self, tenant_id: str, tracker: str, headers: Mapping[str, str], body: bytes
    ) -> bool:
        """Verify a webhook, and wake the followers this process runs of the project it names.

        The tenant's secret comes from the credentials its followers last asked for, never from
        the request: a tenant whose follower hasn't read yet, a switched-off workspace and a bad
        signature are refused alike, and counted together.

        Returns whether the webhook was verified.
        """
        bound = [w for w in self._trackers.bindings if w.tenant_id == tenant_id]
        connections = (self._trackers.connected(workspace) for workspace in bound)
        connection = next((c for c in connections if c is not None), None)
        nudged = None
        if tracker == self._tracker and connection is not None:
            nudged = connection.nudge(headers, body)  # verified before anything is asked
        on = [] if nudged is None else [w for w in bound if await self._trackers.enabled(w)]
        if nudged is None or not on:
            self._telemetry.count(NUDGES_REFUSED, {})
            return False
        for workspace in on:
            woken = self._held.get(workspace)
            if woken is not None and self._trackers.bindings[workspace].project == nudged.project:
                woken.set()
        return True

    async def aclose(self) -> None:
        """Stop every follower, releasing its lease, and start no more."""
        self._closed = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # ─── following ────────────────────────────────────────────────────────────

    def _ended(self, workspace: WorkspaceKey, task: asyncio.Task[None]) -> None:
        # A follower that stopped starts again the next time its workspace is opened.
        self._tasks.pop(workspace, None)
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("following %s/%s's tracker stopped", *workspace, exc_info=error)
            attributes = {**workspace_attributes(*workspace), ERROR_TYPE: type(error).__qualname__}
            self._telemetry.count(FOLLOWERS_STOPPED, attributes)

    async def _may(self, workspace: WorkspaceKey) -> bool:
        """Whether this process may read the workspace's project: on, and its lease taken."""
        return await self._trackers.enabled(workspace) and await self._ledger.acquire_tracker_lease(
            workspace, self._holder, self._ttl
        )

    async def _follow(self, workspace: WorkspaceKey) -> None:
        """Follow a workspace's project whenever this process may, until cancelled.

        It runs in an empty context, as the artifactr followers do (relayr ADR-0023).
        """
        detached = otel_context.attach(otel_context.Context())
        try:
            target = await self._reflexr.open(*workspace, actor=SOURCE)
            while True:
                if await self._may(workspace):
                    try:
                        await self._hold(workspace, target)
                    finally:
                        await self._ledger.release_tracker_lease(workspace, self._holder)
                await asyncio.sleep(self._ttl.total_seconds() / 3)
        finally:
            otel_context.detach(detached)

    async def _hold(self, workspace: WorkspaceKey, target: reflexr.workspace.Workspace) -> None:
        """Poll while the lease holds and the integration is on; return once either is not."""
        woken = self._held[workspace] = asyncio.Event()
        try:
            while True:
                loop = asyncio.get_running_loop()
                began, nudged = loop.time(), woken.is_set()
                woken.clear()
                pause = await self._poll(workspace, target, nudged=nudged)
                if not await self._wait(workspace, woken, began, pause):
                    return
        finally:
            del self._held[workspace]

    async def _wait(
        self, workspace: WorkspaceKey, woken: asyncio.Event, began: float, pause: float
    ) -> bool:
        """Wait for the next poll, renewing the lease; return whether it holds and is on.

        The next poll is an interval after the last began, or a rate limit's pause after it
        ended; or, once a nudge comes, the debounce after the last began.
        """
        loop = asyncio.get_running_loop()
        due = max(began + self._interval.total_seconds(), loop.time() + pause)
        while (left := due - loop.time()) > 0 and not (woken.is_set() and pause <= 0):
            step = min(self._ttl.total_seconds() / 3, left)
            if pause > 0:  # a nudge doesn't cut a rate limit's pause short
                await asyncio.sleep(step)
            else:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(woken.wait(), step)
            if not await self._may(workspace):
                return False
        if woken.is_set():
            await asyncio.sleep(max(0.0, began + DEBOUNCE.total_seconds() - loop.time()))
        return await self._may(workspace)

    async def _poll(
        self, workspace: WorkspaceKey, target: reflexr.workspace.Workspace, *, nudged: bool
    ) -> float:
        """Read the project once; return how many seconds the tracker asks to be left alone.

        A tracker's failure is logged: the next poll reads what this one couldn't.
        """
        fresh = workspace in self._refused
        self._refused.discard(workspace)
        try:
            tracker = await self._trackers.connection(workspace, fresh=fresh)
            with self._telemetry.tracer.start_as_current_span(
                "relayr.trackers.poll", attributes=workspace_attributes(*workspace)
            ):
                found = await _Reading(
                    workspace=workspace,
                    binding=self._trackers.bindings[workspace],
                    tracker=tracker,
                    name=self._tracker,
                    target=target,
                    projection=self._projections.get(workspace),
                    ledger=self._ledger,
                    budget=self._trackers.budget,
                    telemetry=self._telemetry,
                    now=self._clock(),
                    sweep_every=self._sweep_every,
                ).read()
        except RateLimited as error:
            logger.warning("the tracker of %s/%s is rate-limited", *workspace)
            wait = (
                self._interval.total_seconds() if error.retry_after is None else error.retry_after
            )
            return wait + random.uniform(0, 1)
        except Unauthorized:
            logger.warning("the tracker of %s/%s refused its key", *workspace)
            self._refused.add(workspace)
            return 0.0
        except TrackerError as error:
            logger.warning("reading the tracker of %s/%s failed: %r", *workspace, error)
            return 0.0
        if not nudged and found:
            self._telemetry.count(UNNUDGED, workspace_attributes(*workspace), found)
        return 0.0


@dataclass
class _Reading:
    """One poll of a workspace's project, and what it publishes and saves."""

    workspace: WorkspaceKey
    binding: TrackerBinding
    tracker: Tracker
    name: str
    """The tracker's name in events: `plane` or `vikunja`."""

    target: reflexr.workspace.Workspace
    projection: TrackerProjection | None
    ledger: Ledger
    budget: Budget
    telemetry: Telemetry
    now: datetime
    sweep_every: timedelta
    found: int = 0
    """The changes it published that reflexr didn't have, but removals, which no webhook
    announces."""

    saved: list[Snapshot] = field(default_factory=list[Snapshot])
    echoed: dict[str, dict[str, JsonValue]] = field(default_factory=dict[str, dict[str, JsonValue]])
    """Each item's fields read back as relayr wrote them, by the item's key."""

    async def read(self) -> int:
        """Read the project, publish what changed, and return how many changes were new.

        It reads the whole project when the binding is new or its sweep is due, and otherwise
        what changed since a while before its cursor. It stops at the first item whose comments
        the budget has no request left for, and moves its cursor only past what it read.
        """
        tenant, project = self.workspace.tenant_id, self.binding.project
        if not self.budget.take(tenant):
            return self.found
        following = await self.ledger.tracker_following(self.workspace)
        if following is not None and following.project != project:
            await self.ledger.forget_snapshots(self.workspace)
            following = None
        sweeping = following is None or self.now - following.swept_at >= self.sweep_every
        after = None if following is None or sweeping else _back(following.cursor)
        page = await self.tracker.items(project, after)
        ids = None if sweeping else [item.ref.id for item in page.items]
        snapshots = await self.ledger.snapshots(self.workspace, ids)
        read: list[Item] = []
        for item in page.items:
            if not await self._item(item, snapshots.get(item.ref.id), seeding=following is None):
                break
            read.append(item)
        await self.ledger.save_snapshots(self.workspace, self.saved)
        for key, values in self.echoed.items():
            await self.ledger.consume_written(self.workspace, key, values)
        whole = len(read) == len(page.items)
        if sweeping and whole:
            listed = {item.ref.id for item in page.items}
            swept = await self._removed({i: s for i, s in snapshots.items() if i not in listed})
        else:
            swept = False
        # The ledger keeps the furthest cursor: one read behind it, or none, moves nothing.
        cursor = page.next if whole else None
        if not whole and read:
            cursor = Cursor(updated_at=read[-1].updated_at, id=read[-1].ref.id)
        await self.ledger.save_tracker_following(
            self.workspace,
            TrackerFollowing(
                project=project,
                cursor=None if cursor is None else (cursor.updated_at, cursor.id),
                swept_at=self.now if swept or following is None else following.swept_at,
                read_at=self.now,
            ),
        )
        return self.found

    async def _item(self, item: Item, snapshot: Snapshot | None, *, seeding: bool) -> bool:
        """Publish what changed on an item; False, doing nothing, if the budget is out.

        A new binding's first read publishes nothing, but the items changed since its `since`
        as created, and their comments from then on; their comments until then are old.
        """
        new = item.model_dump(mode="json")
        if snapshot is not None and snapshot.item == new:
            return True
        key = item.ref.key
        tracked = None if key is None else await self.ledger.tracked(self.workspace, "item", key)
        chain = None if tracked is None else tracked.correlation_id
        written = {} if tracked is None else tracked.written
        echoed = {f: new[f] for f in FIELDS if f in written and written[f] == new[f]}
        if snapshot is None and seeding:
            self._echoed(key, echoed)
            since = self.binding.since
            if since is not None and item.updated_at >= since and tracked is None:
                await self._publish(self._created(item), chain)
            after = item.updated_at + _JUST_AFTER if since is None else since
            self.saved.append(Snapshot(item_id=item.ref.id, item=new, comments_after=after))
            return True
        moved = snapshot is None or snapshot.item["updated_at"] != new["updated_at"]
        if moved and not self.budget.take(self.workspace.tenant_id):
            return False
        self._echoed(key, echoed)
        if snapshot is None:
            if tracked is None:
                await self._publish(self._created(item), chain)
        else:
            await self._changed(item, snapshot.item, new, echoed, chain)
        after = None if snapshot is None else snapshot.comments_after
        if moved:
            after = await self._comments(item, after, chain)
        self.saved.append(Snapshot(item_id=item.ref.id, item=new, comments_after=after))
        return True

    def _echoed(self, key: str | None, echoed: dict[str, JsonValue]) -> None:
        """Keep the fields read back as relayr wrote them, to consume once the item is saved."""
        if key is not None and echoed:
            self.echoed[key] = echoed

    async def _changed(
        self,
        item: Item,
        old: Mapping[str, JsonValue],
        new: Mapping[str, JsonValue],
        echoed: Mapping[str, JsonValue],
        chain: str | None,
    ) -> None:
        """Publish each field that differs from an item's snapshot, but those relayr wrote.

        Its `actor` is the item's last updater, unless relayr wrote to the item since.
        """
        changed: list[Field] = [name for name in FIELDS if old[name] != new[name]]
        actor = None if echoed.keys() & set(changed) else item.updated_by
        at = item.updated_at.isoformat()
        for name in changed:
            if name not in echoed:
                event = ItemChanged(
                    **self._about(item), field=name, old=old[name], new=new[name], actor=actor
                )
                await self._publish(
                    (event, self._id(item.ref.id, name, canonical(new[name]), at)), chain
                )

    async def _comments(
        self, item: Item, after: datetime | None, chain: str | None
    ) -> datetime | None:
        """Publish an item's comments since `after`, but lattice's; return the last one's time."""
        comments = await self.tracker.comments(item.ref, None)
        for comment in comments:
            if comment.key is None and (after is None or comment.created_at >= after):
                commented = ItemCommented(
                    **self._about(item),
                    comment_id=comment.ref.id,
                    body=comment.body,
                    author=comment.author,
                )
                await self._publish((commented, self._id("comment", comment.ref.id)), chain)
        latest = max((comment.created_at for comment in comments), default=None)
        return after if latest is None or (after is not None and after > latest) else latest

    async def _removed(self, gone: Mapping[str, Snapshot]) -> bool:
        """Publish the items no longer listed, and forget them; False if the budget ran out.

        An item lattice filed is looked for by its key, which finds it archived on Plane, so only
        a deleted one is marked, and filed nothing again.
        """
        forgotten: list[str] = []
        for item_id, snapshot in gone.items():
            item = Item.model_validate(snapshot.item)
            key, deleted, chain = item.ref.key, None, None
            if key is not None:
                if not self.budget.take(self.workspace.tenant_id):
                    break
                deleted = await self.tracker.find(item.ref.project, key) is None
                if deleted:
                    await self.ledger.mark_tracked_deleted(self.workspace, key)
                tracked = await self.ledger.tracked(self.workspace, "item", key)
                chain = None if tracked is None else tracked.correlation_id
            removed = ItemRemoved(**self._about(item), deleted=deleted)
            at = item.updated_at.isoformat()
            await self._publish((removed, self._id(item_id, "removed", at)), chain)
            forgotten.append(item_id)
        await self.ledger.forget_snapshots(self.workspace, forgotten)
        return len(forgotten) == len(gone)

    async def _publish(self, made: tuple[TrackerEvent, str], chain: str | None) -> None:
        """Publish an event by its id, as the projection makes it, in the item's chain if any.

        A projection that raises, or returns one of reflexr's own events, dead-letters it. A
        chain reflexr no longer has leaves the event to start its own.
        """
        event, published_id = made
        try:
            projected = event if self.projection is None else self.projection(event)
            if projected is not None and projected.event_namespace == "reflexr":
                raise Forbidden(f"{projected.event_type} events are recorded by reflexr")
        except Exception as error:  # a projection is the application's code
            await self._dead_letter(event, published_id, error)
            return
        if projected is None:
            return
        try:
            published = await self.target.publish(projected, id=published_id, correlation_id=chain)
        except NotFound:
            # The chain is gone, or the type is one reflexr refuses, which raises again.
            if chain is None:
                raise
            published = await self.target.publish(projected, id=published_id)
        if not published.duplicate and not isinstance(event, ItemRemoved):
            self.found += 1

    async def _dead_letter(self, event: TrackerEvent, published_id: str, error: Exception) -> None:
        logger.warning(
            "could not publish %s of item %s in %s/%s: %r",
            event.event_type,
            event.item_id,
            *self.workspace,
            error,
        )
        letter = TrackerDeadLetter(
            event_id=published_id,
            event_type=event.event_type,
            item_id=event.item_id,
            error=f"{type(error).__name__}: {error}",
        )
        await self.ledger.tracker_dead_letter(self.workspace, letter)
        attributes = {**workspace_attributes(*self.workspace), EVENT_TYPE: event.event_type}
        self.telemetry.count(TRACKER_DEAD_LETTERS, attributes)

    def _about(self, item: Item) -> "_About":
        """What every event says of its item."""
        return _About(
            tracker=self.name,
            project=item.ref.project,
            item_id=item.ref.id,
            number=item.ref.number,
            name=item.ref.name,
            link=self.tracker.link(item.ref),
            key=item.ref.key,
        )

    def _created(self, item: Item) -> tuple[TrackerEvent, str]:
        created = ItemCreated(
            **self._about(item),
            title=item.title,
            description=item.description,
            state=item.state,
            priority=item.priority,
            labels=item.labels,
            assignees=item.assignees,
            actor=item.updated_by,
        )
        return created, self._id(item.ref.id, "created", item.updated_at.isoformat())

    def _id(self, *parts: str) -> str:
        """An event's id: over the tenant, the binding and the tracker, then what it says."""
        tenant, workspace = self.workspace
        return event_id(tenant, workspace, self.binding.project, self.name, *parts)


class _About(TypedDict):
    """The fields every `tracker:` event takes from its item."""

    tracker: str
    project: str
    item_id: str
    number: int
    name: str
    link: str
    key: str | None


_JUST_AFTER: Final = timedelta(microseconds=1)
"""How long after an item's last change, when its binding was first read, its comments are new:
those until then are old, and published by no one."""


def _back(cursor: tuple[datetime, str] | None) -> Cursor | None:
    """Where a poll reads from: a while before the cursor."""
    return None if cursor is None else Cursor(updated_at=cursor[0] - LOOK_BACK, id=cursor[1])
