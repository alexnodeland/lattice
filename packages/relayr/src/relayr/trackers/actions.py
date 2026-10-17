"""The tracker connector's outbound side: a run of a rule files and changes items, once.

[`Trackers.acting`][relayr.trackers.Trackers.acting] gives a run's attempt its
[`TrackerActions`][relayr.trackers.TrackerActions]. Neither tracker deduplicates a retried
request, so the ledger does: every write is made by a key, which the ledger claims before
anything is sent and records what it made. A key is the rule's own, or derived as the outbound
adapter derives its ids (relayr ADR-0019), so a retried attempt makes nothing twice.
"""

import asyncio
import weakref
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from opentelemetry.metrics import MeterProvider
from pydantic import BaseModel, ConfigDict, JsonValue

from reflexr.workspace import Reaction, RunFailure
from relayr.integrations import Enabled, always
from relayr.ledger import Clock, Ledger, TrackedKind, WorkspaceKey, utc_now
from relayr.outbound.actions import NotAllowed
from relayr.outbound.allowlist import Allowlist, Allowlists
from relayr.outbound.ids import Derivation, canonical
from relayr.telemetry import TRACKER_LOOPS, Telemetry, workspace_attributes
from relayr.trackers.budget import Budget
from relayr.trackers.port import (
    CommentKey,
    CommentRef,
    Item,
    ItemDraft,
    ItemFields,
    ItemKey,
    ItemRef,
    NotFound,
    Priority,
    ProjectId,
    RateLimited,
    Refused,
    State,
    Tracker,
    TrackerCredentials,
    Unauthorized,
    Unavailable,
)

CLAIM_TTL: Final = timedelta(seconds=30)
"""How long a key's claim holds without a record before another attempt may take it again: longer
than `WRITING`, which bounds the writes made under it."""

WRITING: Final = timedelta(seconds=20)
"""How long a claim's writes may take, all told: well inside the claim, so a claim taken again
never overlaps a write relayr is still making. A request the tracker finishes after relayr gave
up on it can still land later."""

UNAVAILABLE: Final = "tracker_unavailable"
"""The reason of a failure whose write may have landed: the tracker didn't answer in time."""

CREDENTIALS_TTL: Final = timedelta(minutes=5)
"""How long a tenant's credentials are used before they are asked for again; a key the tracker
refuses asks again at once."""

LOOP_CAP: Final = 20
"""How many writes relayr makes to one item within `LOOP_WINDOW`: the next fails its run for
good, as `tracker_loop`. It backs the echo filter, for what the filter can't see."""

LOOP_WINDOW: Final = timedelta(hours=1)
"""What `LOOP_CAP` is per."""

type Connect = Callable[[TrackerCredentials, str], Tracker]
"""Makes a lattice workspace's adapter from its tenant's credentials and its source: `plane(http)`,
`vikunja(http)`, or the fake's `connect`."""

type Credentials = Callable[[str], Awaitable[TrackerCredentials]]
"""Returns a tenant's tracker credentials, from wherever the deployment keeps them."""


class TrackerBinding(BaseModel):
    """The tracker project a workspace's runs file into, and whose changes its follower reads."""

    model_config = ConfigDict(frozen=True)

    project: ProjectId
    state: State | None = None
    """Where an item starts unless the rule says; by default the tracker's default state."""

    priority: Priority | None = None
    """An item's priority unless the rule says; by default `none`."""

    labels: tuple[str, ...] = ()
    """Labels every item filed has, beside the rule's."""

    since: datetime | None = None
    """When its follower first reads the project, the items changed since are published as
    created; by default none is, and only what changes after is published."""


class Deleted(BaseModel):
    """What `ensure_item` returns for a key whose item a person deleted: it files nothing."""

    model_config = ConfigDict(frozen=True)

    key: ItemKey


class TrackerRefused(RunFailure):
    """The tracker refused a write as invalid, or about something missing.

    An agent's tools hand it back to the model, which can do otherwise; from a function action,
    it fails the attempt, which is retried. Its reason is `tracker_refused` or `tracker_not_found`.
    """

    def __init__(self, error: Refused | NotFound) -> None:
        reason = "tracker_not_found" if isinstance(error, NotFound) else "tracker_refused"
        super().__init__(str(error), reason=reason)


class Trackers:
    """Lets the runs of rules write to their workspace's tracker, within their allowlists.

    Give it to the actions that file items, as their dependency or through
    [`TrackerCapability`][relayr.trackers.TrackerCapability].

    Args:
        ledger: Where keys are claimed before each write and what they made is recorded.
        connect: Makes a workspace's adapter, as `plane(http)` or `vikunja(http)` does.
        credentials: Returns a tenant's credentials; asked again every five minutes, and after
            the tracker refuses a key.
        bindings: The tracker project each workspace files into. A workspace with none files
            nothing.
        allowlists: Each rule's allowlist, as [`Outbound`][relayr.outbound.Outbound] takes them.
            A rule writes to its tracker only if its allowlist's `trackers` is set.
        integration: The tracker's key among the application's integrations:
            `relayr.plane.INTEGRATION` or `relayr.vikunja.INTEGRATION`.
        enabled: Whether the integration runs in a workspace, asked before anything is done
            there. By default it runs everywhere.
        budget: How many requests a minute each tenant's key may make from this process, all
            told: runs' writes spend it first, and the followers' polls take what is left.
            Plane allows 60 by default.
        clock: Returns the current time, which credentials expire and the budget is measured by.
        meter_provider: Where the count of writes refused by the cap on loops goes. Defaults to
            the global provider.

    Raises:
        ValueError: If a key of ``allowlists`` is neither a rule's name nor a whole namespace's.
    """

    def __init__(
        self,
        ledger: Ledger,
        *,
        connect: Connect,
        credentials: Credentials,
        bindings: Mapping[WorkspaceKey, TrackerBinding],
        allowlists: Mapping[str, Allowlist] | None = None,
        integration: str,
        enabled: Enabled = always,
        budget: int = 40,
        clock: Clock = utc_now,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self._ledger = ledger
        self._integration = integration
        self._enabled = enabled
        self._connections = _Connections(connect, credentials, clock)
        self._bindings = MappingProxyType(dict(bindings))
        self._allowlists = Allowlists(allowlists)
        self._budget = Budget(budget, clock)
        self._telemetry = Telemetry(meter_provider=meter_provider)
        self._acting: weakref.WeakKeyDictionary[Reaction[Any], TrackerActions] = (
            weakref.WeakKeyDictionary()
        )

    def acting(self, reaction: Reaction[Any]) -> "TrackerActions":
        """Return what an attempt of a run may do in its tracker; the same for the attempt."""
        actions = self._acting.get(reaction)
        if actions is None:
            key = WorkspaceKey(reaction.workspace.tenant_id, reaction.workspace.workspace_id)
            actions = TrackerActions(
                reaction,
                self,
                self._bindings.get(key),
                self._allowlists.of(reaction.run.rule),
                self._telemetry,
            )
            self._acting[reaction] = actions
        return actions

    # ─── what the followers and the webhooks' router read ─────────────────────

    @property
    def ledger(self) -> Ledger:
        """Where keys are claimed, and what the followers read is kept."""
        return self._ledger

    @property
    def integration(self) -> str:
        """The tracker's key among the application's integrations, such as `tracker:plane`."""
        return self._integration

    @property
    def bindings(self) -> Mapping[WorkspaceKey, TrackerBinding]:
        """The tracker project each bound workspace files into and reads."""
        return self._bindings

    @property
    def budget(self) -> Budget:
        """The requests each tenant's key may make from this process a minute."""
        return self._budget

    async def enabled(self, workspace: WorkspaceKey) -> bool:
        """Whether the integration runs in a workspace: asked before anything is done there."""
        return await self._enabled(*workspace, self._integration)

    async def connection(self, workspace: WorkspaceKey, *, fresh: bool = False) -> Tracker:
        """A workspace's adapter; with its tenant's credentials asked for again if `fresh`."""
        return await self._connections.get(workspace, fresh=fresh)

    def connected(self, workspace: WorkspaceKey) -> Tracker | None:
        """A workspace's adapter if one was made, without asking for credentials."""
        return self._connections.made(workspace)


class TrackerActions:
    """What one attempt of a run does in its workspace's tracker. Get it with `Trackers.acting`.

    Every method needs the rule's allowlist to allow trackers, the workspace to be bound, and the
    integration to be enabled there; otherwise it is `NotAllowed`, before the ledger or the
    tracker is touched.
    Each fails the attempt, to be retried, when the tracker is unavailable or rate-limited;
    raises [`TrackerRefused`][relayr.trackers.TrackerRefused] when it refuses a write as invalid
    or about something missing; and fails the run for good when it refuses the tenant's key.
    """

    def __init__(
        self,
        reaction: Reaction[Any],
        trackers: Trackers,
        binding: TrackerBinding | None,
        allowlist: Allowlist,
        telemetry: Telemetry,
    ) -> None:
        self._reaction = reaction
        self._trackers = trackers
        self._telemetry = telemetry
        self._ledger = trackers.ledger
        self._key = WorkspaceKey(reaction.workspace.tenant_id, reaction.workspace.workspace_id)
        self._binding = binding
        self._allowlist = allowlist
        self._derive = Derivation(reaction).derive

    # ─── what a run does ──────────────────────────────────────────────────────

    async def ensure_item(
        self, draft: ItemDraft, *, key: ItemKey | None = None
    ) -> ItemRef | Deleted:
        """File an item, once: or return the one its key filed, unless a person deleted it.

        The key is claimed in the ledger before the tracker is asked for it, then the tracker
        is asked for an item the key filed, and only then is one created. An item filed earlier
        is read first: a closed or archived one is returned, for the rule to reopen if it will;
        a deleted one is [`Deleted`][relayr.trackers.Deleted], and files nothing.

        Args:
            draft: The item, with the binding's defaults for what it leaves unset.
            key: What the item is filed by. By default it is derived from the run and the
                draft; a key of the rule's own, as ``dead-letter/<rule>``, files later runs into
                the same item.

        Raises:
            RunFailure: If another attempt claimed the key within the last 30 s and hasn't
                recorded its item, so the attempt is retried. A write the tracker refused
                releases the key's claim, so the rule may file by it again at once.
        """
        binding = await self._bound()
        key = key or self._derive("item", canonical(draft.model_dump(mode="json")))
        tracked = await self._ledger.tracked(self._key, "item", key)
        if tracked is not None and tracked.deleted:
            return Deleted(key=key)
        if tracked is None or tracked.ref is None:
            return await self._file(binding, key, draft)
        ref = ItemRef.model_validate(tracked.ref)
        if await self._call(lambda tracker: tracker.item(ref)) is None:
            await self._ledger.mark_tracked_deleted(self._key, key)
            return Deleted(key=key)
        return ref

    async def comment(
        self, item: ItemRef, body: str, *, key: CommentKey | None = None
    ) -> CommentRef:
        """Post a comment on an item, once.

        Args:
            item: The item.
            body: What it says, as HTML.
            key: What the comment is posted by; by default derived from the run, the item and
                the text.
        """
        await self._bound()
        key = key or self._derive("comment", item.id, canonical(body))
        tracked = await self._ledger.tracked(self._key, "comment", key)
        if tracked is not None and tracked.ref is not None:
            return CommentRef.model_validate(tracked.ref)
        async with self._claimed("comment", key):
            await self._capped(item.id)
            ref = await self._call(lambda tracker: tracker.comment(item, key, body))
            kept = await self._ledger.record_tracked(self._key, "comment", key, _json(ref))
        return CommentRef.model_validate(kept or _json(ref))

    async def set_state(self, item: ItemRef, state: State) -> None:
        """Move an item to a state, unless it is there: a keyed edit, as `update` makes."""
        await self.update(item, ItemFields(state=state))

    async def update(self, item: ItemRef, fields: ItemFields) -> None:
        """Set the fields given on an item lattice filed, unless each holds its value already.

        The item is read, and only the fields that differ are sent. Their values are recorded on
        the item's key before they are, so what comes back from the tracker can be told from a
        person's change; a change the tracker refuses puts back what was recorded before it.

        Raises:
            RunFailure: For good, if the item wasn't filed by lattice, which has no key for it.
            TrackerRefused: If the item was deleted, or the tracker refuses the change.
        """
        await self._bound()
        if item.key is None:
            raise RunFailure(
                f"{self._rule} changes only the items it filed, by their keys",
                reason="tracker_not_filed",
                permanent=True,
            )
        key = item.key
        current = await self._call(lambda tracker: tracker.item(item))
        if current is None:
            await self._ledger.mark_tracked_deleted(self._key, key)
            raise TrackerRefused(NotFound(f"item {item.name} was deleted"))
        changed = _differing(current, fields, await self._trackers.connection(self._key))
        if not changed:
            return
        await self._capped(item.id)
        tracked = await self._ledger.tracked(self._key, "item", key)
        before = {} if tracked is None else tracked.written
        await self._ledger.record_written(self._key, key, changed)
        change = ItemFields.model_validate(changed)
        try:
            await self._call(lambda tracker: tracker.update(item, change))
        except RunFailure as failure:
            if failure.reason == UNAVAILABLE:
                raise
            # The change never landed: what relayr set before it is what it last set.
            await self._ledger.forget_written(self._key, key, set(changed) - set(before))
            await self._ledger.record_written(
                self._key, key, {name: before[name] for name in changed if name in before}
            )
            raise

    async def read(self, item: ItemRef) -> Item | None:
        """Return an item's snapshot, archived or not, or None if it was deleted."""
        await self._bound()
        return await self._call(lambda tracker: tracker.item(item))

    async def filed(self, key: ItemKey) -> ItemRef | None:
        """Return the item a key filed, or None if it filed none, or a person deleted it."""
        await self._bound()
        tracked = await self._ledger.tracked(self._key, "item", key)
        if tracked is None or tracked.ref is None or tracked.deleted:
            return None
        return ItemRef.model_validate(tracked.ref)

    async def link(self, item: ItemRef) -> str:
        """Return the item's address in the tracker's web app."""
        await self._bound()
        tracker = await self._trackers.connection(self._key)
        return tracker.link(item)

    # ─── how ──────────────────────────────────────────────────────────────────

    @property
    def _rule(self) -> str:
        return self._reaction.run.rule

    async def _bound(self) -> TrackerBinding:
        """The workspace's binding, if the rule may write to it and the integration runs there.

        The one place every write and read checks first, before the ledger or the tracker:
        the rule's allowlist, the workspace's binding, and whether the integration is enabled
        in the workspace.
        """
        if not self._allowlist.trackers:
            raise NotAllowed(f"{self._rule} may not write to its tracker")
        if self._binding is None:
            raise NotAllowed(f"workspace {self._key.workspace_id} has no tracker project")
        if not await self._trackers.enabled(self._key):
            integration = self._trackers.integration
            raise NotAllowed(f"{integration} is off in workspace {self._key.workspace_id}")
        return self._binding

    async def _capped(self, item_id: str) -> None:
        """Count a write about to be made to an item, and refuse it past the cap on loops.

        Raises:
            RunFailure: For good, as `tracker_loop`, past `LOOP_CAP` writes to the item within
                `LOOP_WINDOW`.
        """
        made = await self._ledger.record_tracker_write(self._key, item_id, within=LOOP_WINDOW)
        if made > LOOP_CAP:
            self._telemetry.count(TRACKER_LOOPS, workspace_attributes(*self._key))
            raise RunFailure(
                f"relayr wrote to item {item_id} {LOOP_CAP} times within {LOOP_WINDOW}",
                reason="tracker_loop",
                permanent=True,
            )

    @asynccontextmanager
    async def _claimed(self, kind: TrackedKind, key: str) -> AsyncGenerator[None]:
        """Claim a key for the writes made within, which end well inside the claim.

        A write the tracker certainly didn't take releases the claim, so the run may write by the
        key again at once; one that may have landed keeps it, for its 30 s.

        Raises:
            RunFailure: If another attempt holds a fresh claim, so this one is retried; or if the
                writes took longer than `WRITING`, as `tracker_unavailable`.
        """
        run = self._reaction.run
        claimed = await self._ledger.claim_tracked(
            self._key, kind, key, run.correlation_id, stale_after=CLAIM_TTL
        )
        if not claimed:
            raise RunFailure(
                f"{kind} {key} is being written by another attempt", reason="tracker_claimed"
            )
        try:
            async with asyncio.timeout(WRITING.total_seconds()):
                yield
        except TimeoutError as error:
            raise RunFailure(f"writing {kind} {key} took too long", reason=UNAVAILABLE) from error
        except RunFailure as failure:
            if failure.reason != UNAVAILABLE:
                await self._ledger.release_tracked(self._key, kind, key)
            raise

    async def _file(self, binding: TrackerBinding, key: ItemKey, draft: ItemDraft) -> ItemRef:
        """Claim a key, then find the item it filed, or create one, and record it.

        An item found was filed by an attempt that stopped before it recorded it, perhaps before
        it labelled it, as Vikunja labels after it creates; its labels are made the draft's. The
        values filed are recorded first, as the tracker will hold them, so the follower takes the
        item, however far along it reads it, for relayr's own.
        """
        filed = ItemDraft(
            title=draft.title,
            description=draft.description,
            state=draft.state or binding.state,
            priority=draft.priority or binding.priority,
            labels=tuple(dict.fromkeys((*binding.labels, *draft.labels))),
        )
        project = binding.project
        tracker = await self._trackers.connection(self._key)
        async with self._claimed("item", key):
            await self._ledger.record_written(self._key, key, _filed(filed, tracker))
            found = await self._call(lambda tracker: tracker.find(project, key))
            ref = found or await self._call(lambda tracker: tracker.create(project, key, filed))
            kept = await self._ledger.record_tracked(self._key, "item", key, _json(ref))
        item = ItemRef.model_validate(kept or _json(ref))
        if found is not None:
            await self.update(item, ItemFields(labels=filed.labels))
        return item

    async def _call[T](self, request: Callable[[Tracker], Awaitable[T]]) -> T:
        """Make a request, its errors as a run's failures.

        The tenant's credentials are asked for again, and the request made again, once, if the
        tracker refuses its key.
        """
        for fresh in (False, True):
            tracker = await self._trackers.connection(self._key, fresh=fresh)
            self._trackers.budget.spend(self._key.tenant_id)
            try:
                return await request(tracker)
            except Unauthorized:
                continue
            except RateLimited as error:
                raise RunFailure(str(error), reason="tracker_rate_limited") from error
            except Unavailable as error:
                raise RunFailure(str(error), reason=UNAVAILABLE) from error
            except (Refused, NotFound) as error:
                raise TrackerRefused(error) from error
        raise RunFailure(
            "the tracker refused the tenant's key", reason="tracker_unauthorized", permanent=True
        )


class _Connections:
    """Each workspace's adapter, made from its tenant's credentials, which are kept a while."""

    def __init__(self, connect: Connect, credentials: Credentials, clock: Clock) -> None:
        self._connect = connect
        self._credentials = credentials
        self._clock = clock
        self._asked: dict[str, tuple[TrackerCredentials, datetime]] = {}
        self._made: dict[WorkspaceKey, tuple[TrackerCredentials, Tracker]] = {}

    def made(self, workspace: WorkspaceKey) -> Tracker | None:
        """A workspace's adapter, if one was made."""
        made = self._made.get(workspace)
        return None if made is None else made[1]

    async def get(self, workspace: WorkspaceKey, *, fresh: bool = False) -> Tracker:
        """A workspace's adapter; with its tenant's credentials asked for again if `fresh`."""
        credentials = await self._of(workspace.tenant_id, fresh=fresh)
        made = self._made.get(workspace)
        if made is None or made[0] != credentials:
            source = f"lattice:{workspace.tenant_id}/{workspace.workspace_id}"
            made = (credentials, self._connect(credentials, source))
            self._made[workspace] = made
        return made[1]

    async def _of(self, tenant: str, *, fresh: bool) -> TrackerCredentials:
        now = self._clock()
        asked = self._asked.get(tenant)
        if fresh or asked is None or asked[1] <= now - CREDENTIALS_TTL:
            asked = (await self._credentials(tenant), now)
            self._asked[tenant] = asked
        return asked[0]


def _json(model: BaseModel) -> dict[str, JsonValue]:
    return model.model_dump(mode="json")


def _held(fields: ItemFields, tracker: Tracker) -> dict[str, JsonValue]:
    """Fields' values as JSON, as the tracker will hold them: labels as a sorted set."""
    held = fields.model_dump(mode="json", exclude_none=True)
    if fields.labels is not None:
        held["labels"] = sorted(set(fields.labels))
    if fields.state is not None:
        held["state"] = tracker.holds(fields.state)
    return held


def _filed(draft: ItemDraft, tracker: Tracker) -> dict[str, JsonValue]:
    """The values an item is filed with, as the tracker will hold them."""
    return _held(ItemFields.model_validate(draft.model_dump()), tracker)


def _differing(current: Item, fields: ItemFields, tracker: Tracker) -> dict[str, JsonValue]:
    """The fields whose values, as the tracker will hold them, differ from an item's."""
    wanted = _held(fields, tracker)
    held = current.model_dump(mode="json", include=set(wanted))
    return {name: value for name, value in wanted.items() if held[name] != value}
