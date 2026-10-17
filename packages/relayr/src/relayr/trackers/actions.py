"""The tracker connector's outbound side: a run of a rule files and changes items, once.

[`Trackers.acting`][relayr.trackers.Trackers.acting] gives a run's attempt its
[`TrackerActions`][relayr.trackers.TrackerActions]. Neither tracker deduplicates a retried
request, so the ledger does: every write is made by a key, which the ledger claims before
anything is sent and records what it made. A key is the rule's own, or derived as the outbound
adapter derives its ids (relayr ADR-0019), so a retried attempt makes nothing twice.
"""

import weakref
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, JsonValue

from reflexr.workspace import Reaction, RunFailure
from relayr.ledger import Clock, Ledger, TrackedKind, WorkspaceKey, utc_now
from relayr.outbound.actions import NotAllowed
from relayr.outbound.allowlist import Allowlist, Allowlists
from relayr.outbound.ids import Derivation, canonical
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
"""How long a key's claim holds without a record before another attempt may take it again:
three times an adapter's 10 s request timeout."""

CREDENTIALS_TTL: Final = timedelta(minutes=5)
"""How long a tenant's credentials are used before they are asked for again; a key the tracker
refuses asks again at once."""

type Connect = Callable[[TrackerCredentials, str], Tracker]
"""Makes a lattice workspace's adapter from its tenant's credentials and its source: an adapter's
class, as `PlaneTracker`, or the fake's `connect`."""

type Credentials = Callable[[str], Awaitable[TrackerCredentials]]
"""Returns a tenant's tracker credentials, from wherever the deployment keeps them."""


class TrackerBinding(BaseModel):
    """The tracker project a workspace's runs file into, and what its items have by default."""

    model_config = ConfigDict(frozen=True)

    project: ProjectId
    state: State | None = None
    """Where an item starts unless the rule says; by default the tracker's default state."""

    priority: Priority | None = None
    """An item's priority unless the rule says; by default `none`."""

    labels: tuple[str, ...] = ()
    """Labels every item filed has, beside the rule's."""


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
        connect: Makes a workspace's adapter, as `PlaneTracker` or `VikunjaTracker` does.
        credentials: Returns a tenant's credentials; asked again every five minutes, and after
            the tracker refuses a key.
        bindings: The tracker project each workspace files into. A workspace with none files
            nothing.
        allowlists: Each rule's allowlist, as [`Outbound`][relayr.outbound.Outbound] takes them.
            A rule writes to its tracker only if its allowlist's `trackers` is set.
        clock: Returns the current time, which credentials expire by.

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
        clock: Clock = utc_now,
    ) -> None:
        self._ledger = ledger
        self._connections = _Connections(connect, credentials, clock)
        self._bindings = dict(bindings)
        self._allowlists = Allowlists(allowlists)
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
                self._ledger,
                self._connections,
                self._bindings.get(key),
                self._allowlists.of(reaction.run.rule),
            )
            self._acting[reaction] = actions
        return actions


class TrackerActions:
    """What one attempt of a run does in its workspace's tracker. Get it with `Trackers.acting`.

    Every method needs the rule's allowlist to allow trackers, and the workspace to be bound.
    Each fails the attempt, to be retried, when the tracker is unavailable or rate-limited;
    raises [`TrackerRefused`][relayr.trackers.TrackerRefused] when it refuses a write as invalid
    or about something missing; and fails the run for good when it refuses the tenant's key.
    """

    def __init__(
        self,
        reaction: Reaction[Any],
        ledger: Ledger,
        connections: "_Connections",
        binding: TrackerBinding | None,
        allowlist: Allowlist,
    ) -> None:
        self._reaction = reaction
        self._ledger = ledger
        self._connections = connections
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
                recorded its item, so the attempt is retried.
        """
        binding = self._bound()
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
        self._bound()
        key = key or self._derive("comment", item.id, canonical(body))
        tracked = await self._ledger.tracked(self._key, "comment", key)
        if tracked is not None and tracked.ref is not None:
            return CommentRef.model_validate(tracked.ref)
        await self._claim("comment", key)
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
        self._bound()
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
        changed = _differing(current, fields)
        if not changed:
            return
        tracked = await self._ledger.tracked(self._key, "item", key)
        before = {} if tracked is None else tracked.written
        await self._ledger.record_written(self._key, key, changed)
        change = ItemFields.model_validate(changed)
        try:
            await self._call(lambda tracker: tracker.update(item, change))
        except TrackerRefused:
            # The change never landed: what relayr set before it is what it last set.
            await self._ledger.forget_written(self._key, key, set(changed) - set(before))
            await self._ledger.record_written(
                self._key, key, {name: before[name] for name in changed if name in before}
            )
            raise

    async def read(self, item: ItemRef) -> Item | None:
        """Return an item's snapshot, archived or not, or None if it was deleted."""
        self._bound()
        return await self._call(lambda tracker: tracker.item(item))

    async def filed(self, key: ItemKey) -> ItemRef | None:
        """Return the item a key filed, or None if it filed none, or a person deleted it."""
        self._bound()
        tracked = await self._ledger.tracked(self._key, "item", key)
        if tracked is None or tracked.ref is None or tracked.deleted:
            return None
        return ItemRef.model_validate(tracked.ref)

    async def link(self, item: ItemRef) -> str:
        """Return the item's address in the tracker's web app."""
        self._bound()
        tracker = await self._connections.get(self._key)
        return tracker.link(item)

    # ─── how ──────────────────────────────────────────────────────────────────

    @property
    def _rule(self) -> str:
        return self._reaction.run.rule

    def _bound(self) -> TrackerBinding:
        """The workspace's binding, if the rule may write to it."""
        if not self._allowlist.trackers:
            raise NotAllowed(f"{self._rule} may not write to its tracker")
        if self._binding is None:
            raise NotAllowed(f"workspace {self._key.workspace_id} has no tracker project")
        return self._binding

    async def _claim(self, kind: TrackedKind, key: str) -> None:
        """Claim a key before writing by it.

        Raises:
            RunFailure: If another attempt holds a fresh claim, so this one is retried.
        """
        run = self._reaction.run
        claimed = await self._ledger.claim_tracked(
            self._key, kind, key, run.correlation_id, stale_after=CLAIM_TTL
        )
        if not claimed:
            raise RunFailure(
                f"{kind} {key} is being written by another attempt", reason="tracker_claimed"
            )

    async def _file(self, binding: TrackerBinding, key: ItemKey, draft: ItemDraft) -> ItemRef:
        """Claim a key, then find the item it filed, or create one, and record it."""
        await self._claim("item", key)
        filed = ItemDraft(
            title=draft.title,
            description=draft.description,
            state=draft.state or binding.state,
            priority=draft.priority or binding.priority,
            labels=tuple(dict.fromkeys((*binding.labels, *draft.labels))),
        )
        project = binding.project
        ref = await self._call(lambda tracker: tracker.find(project, key))
        if ref is None:
            ref = await self._call(lambda tracker: tracker.create(project, key, filed))
        kept = await self._ledger.record_tracked(self._key, "item", key, _json(ref))
        return ItemRef.model_validate(kept or _json(ref))

    async def _call[T](self, request: Callable[[Tracker], Awaitable[T]]) -> T:
        """Make a request, its errors as a run's failures.

        The tenant's credentials are asked for again, and the request made again, once, if the
        tracker refuses its key.
        """
        for fresh in (False, True):
            tracker = await self._connections.get(self._key, fresh=fresh)
            try:
                return await request(tracker)
            except Unauthorized:
                continue
            except RateLimited as error:
                raise RunFailure(str(error), reason="tracker_rate_limited") from error
            except Unavailable as error:
                raise RunFailure(str(error), reason="tracker_unavailable") from error
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


def _differing(current: Item, fields: ItemFields) -> dict[str, JsonValue]:
    """The fields whose values differ from an item's, as JSON; labels as a sorted set."""
    wanted = fields.model_dump(mode="json", exclude_none=True)
    if "labels" in wanted:
        wanted["labels"] = sorted(set(fields.labels or ()))
    held = current.model_dump(mode="json", include=set(wanted))
    return {name: value for name, value in wanted.items() if held[name] != value}
