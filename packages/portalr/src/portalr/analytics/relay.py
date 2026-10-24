"""The relay: the only way a browser's events reach portalr's analytics (lattice RFC-0008, P2-P3).

``POST /portalr/v1/analytics/session`` signs a session id for the signed-in person, and
``POST /portalr/v1/events`` takes a batch of their events in a tenant they belong to. It drops
the batch unless the person has said yes; it refuses one too large, or past their pace; and of
each event it keeps only what the registry names: a route only as the app's router names it, and
no value that holds an email address. The tenant is the request's, checked with grantr, never the
browser's; no address or browser is kept.

``GET`` and ``PUT /portalr/v1/analytics/consent`` read and record the person's answer. Saying no
deletes their events at once, by their keyed hash.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from grantr.core import AuditFilter, MemberRemoved, User
from grantr.grants import Grants
from portalr.analytics.consent import Consent
from portalr.analytics.limiter import InMemoryRateLimiter, RateLimiter
from portalr.analytics.replay import ReplayBatch, inlined, unmasked
from portalr.readers.analytics import REGISTRY, Analytics, distinct_id
from portalr.readers.umami import Umami

ROUTES: Final = frozenset(
    json.loads(resources.files("portalr.analytics").joinpath("routes.json").read_text())["routes"]
)
"""The app's routes, as its router names them: the only routes recorded."""

MOST_EVENTS: Final = 20
"""How many events one request may carry."""

MOST_BYTES: Final = 16 * 1024
"""How large one request's body may be."""

MOST_VALUE: Final = 200
"""How long one value may be, in characters."""

SESSION_HOURS: Final = 24
"""How long a session id portalr signed is taken."""

Short = Annotated[str, StringConstraints(max_length=MOST_VALUE)]


class Event(BaseModel):
    """One event, as a browser sends it: its name, the route it was on, and the registry's keys."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    event: Annotated[str, StringConstraints(max_length=64)]
    route: Short | None = None
    props: Annotated[
        dict[Annotated[str, StringConstraints(max_length=64)], Short], Field(max_length=10)
    ] = {}


class Batch(BaseModel):
    """A browser's events, in the session portalr signed for it."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    session: Annotated[str, StringConstraints(max_length=128)]
    events: Annotated[list[Event], Field(min_length=1, max_length=MOST_EVENTS)]


class Relayed(BaseModel):
    """What became of a batch: how many events were recorded, and how many were dropped."""

    model_config = ConfigDict(frozen=True)

    recorded: int
    dropped: int


class Session(BaseModel):
    """A session id portalr signed for the person; the browser sends it with every batch."""

    model_config = ConfigDict(frozen=True)

    session: str


class Answer(BaseModel):
    """A person's answer to product analytics: yes, or no."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    given: bool


class Consented(Answer):
    """A person's answer, as read: and whether a deletion their no asked for is still to be done."""

    deleting: bool = False


class Answered(Answer):
    """A person's answer, recorded; on a no, whether their events were deleted."""

    deleted: bool | None = None


log = logging.getLogger("portalr.analytics")

MOST_COPIES: Final = 100
"""How many copies to Umami may be sending at once: past it, a batch's copy is dropped, not
queued, so an Umami that is slow holds no more than this."""
REMOVAL_GRACE: Final = timedelta(seconds=30)
"""How long after a removal its deletion waits: a batch the relay accepted just before it, which
ClickHouse gathers for up to a second, has landed by then, and is deleted with the rest."""

REMOVAL_MARGIN: Final = timedelta(seconds=5)
"""How far past a removal its deletion reaches: events are stamped by the replica that relayed
them, whose clock may run a little ahead of the one that removed the person."""

REMOVALS: Final = AuditFilter(types={"member_removed"})
"""The entries of grantr's audit log that owe a deletion."""


@dataclass(frozen=True)
class Relay:
    """What the relay needs: the analytics store, people's answers, and their pace.

    Args:
        analytics: ClickHouse's analytics, with the deployment's key.
        consent: People's answers, and the deletions owed them, in the application's database.
        limiter: How many events a person may send, and how fast.
        requests: How many requests a person may make, events or answers, and how fast: asked
            before anything else, so even a refused or a dropped request costs only a count.
        deletes: How many deletions a person's answers may set off, and how fast: past it, a
            deletion stays owed for the background pass, and an answer sets off no mutation.
    """

    analytics: Analytics
    consent: Consent
    limiter: RateLimiter
    requests: RateLimiter = field(
        default_factory=lambda: InMemoryRateLimiter(per_second=1, burst=20)
    )
    deletes: RateLimiter = field(
        default_factory=lambda: InMemoryRateLimiter(per_second=10 / 3600, burst=10)
    )
    replay_limiter: RateLimiter = field(
        default_factory=lambda: InMemoryRateLimiter(per_second=128 * 1024, burst=1024 * 1024)
    )
    """How many bytes of replay a person may send: a batch costs its size, or 8 KiB if smaller."""
    umami: Umami | None = None
    """Umami, sent a copy of each consented event, for operators' journeys (portalr ADR-0076);
    a person's deletion deletes their sessions there too."""
    replay: Consent | None = None
    """People's answers to session replay, apart from analytics' (portalr ADR-0077); with Umami,
    the deployment records replays. Without it, there is no replay."""
    grants: Grants | None = None
    """grantr, whose audit log the background pass reads for the removals it hasn't owed yet
    (portalr ADR-0075). Without it, no removal deletes anything."""
    copies: set[asyncio.Future[None]] = field(
        default_factory=lambda: set[asyncio.Future[None]](), repr=False, compare=False
    )
    """The copies to Umami still being sent, kept so none is lost before it is done."""

    def sign(self, user_id: str, *, now: float | None = None) -> str:
        """A new session id for the person, signed so no one else can send under it."""
        nonce = f"{int(now if now is not None else time.time())}-{secrets.token_hex(8)}"
        return f"{nonce}.{self._signature(user_id, nonce)}"

    def session_of(self, user_id: str, signed: str, *, now: float | None = None) -> str | None:
        """The session id a signed one names, if it is the person's and still fresh; else None."""
        nonce, _, signature = signed.partition(".")
        expected = self._signature(user_id, nonce)
        # Bytes, so any text a browser sends is compared, never raised on.
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        started, _, _ = nonce.partition("-")
        age = (now if now is not None else time.time()) - int(started)
        return nonce if 0 <= age < SESSION_HOURS * 3600 else None

    def _signature(self, user_id: str, nonce: str) -> str:
        message = f"session\0{user_id}\0{nonce}".encode()
        return hmac.new(self.analytics.key, message, hashlib.sha256).hexdigest()[:32]

    async def answer(self, user_id: str, *, yes: bool) -> Answered:
        """Record the person's answer; a yes taken back deletes their events, or owes it."""
        debt = await self.consent.give(user_id, yes=yes)
        if yes:
            return Answered(given=True)
        if self.replay is not None and await self.replay.given(user_id):
            # Replay rests on analytics' yes: a no to analytics is a no to replay too, owed until
            # the person's sessions in Umami, their replays with them, are gone.
            replay_debt = await self.replay.give(user_id, yes=False)
            if replay_debt:
                await self.settle_replay(user_id, replay_debt)
        return Answered(given=False, deleted=await self.settle(user_id, debt) if debt else None)

    async def answer_replay(self, user_id: str, *, yes: bool) -> Answered:
        """Record the person's answer to replay; a yes taken back deletes their replays, or owes it.

        Raises:
            ValueError: If it is a yes from a person who hasn't said yes to analytics.
        """
        if self.replay is None:
            raise ValueError("this deployment records no replays")
        if yes and not await self.consent.given(user_id):
            raise ValueError("replay needs product analytics' yes first")
        debt = await self.replay.give(user_id, yes=yes)
        if yes:
            if not await self.consent.given(user_id):
                # An analytics no landed between the check and the write: replay never outlives it.
                await self.settle_replay(user_id, await self.replay.give(user_id, yes=False) or 0)
                raise ValueError("replay needs product analytics' yes first")
            return Answered(given=True)
        return Answered(
            given=False, deleted=await self.settle_replay(user_id, debt) if debt else None
        )

    async def settle_replay(self, user_id: str, debt: int) -> bool:
        """Delete the person's replays, for deletion `debt`: whether it was done.

        Umami deletes a replay with the session it is in, so this deletes the person's sessions
        there, with their journeys; ClickHouse's events, the record, stay. Undone, it stays owed.
        """
        if self.replay is None:
            return False
        if self.umami is not None and not await self.umami.forget(self._person(user_id)):
            return False
        await self.replay.settled(user_id, debt)
        return True

    async def record_replay(
        self,
        tenant: str,
        user_id: str,
        batch: ReplayBatch,
        sheets: Mapping[str, str] | None = None,
    ) -> Relayed:
        """Forward the person's replay events to Umami, if they said yes to both, and all is masked.

        A batch with any value unmasked is dropped whole, and said by the key's first 40
        characters, never its value. The copy is sent in the background, as the events' is; their
        answers are read again after it, and a no that landed meanwhile deletes it.
        """
        dropped = Relayed(recorded=0, dropped=len(batch.events))
        if self.replay is None or self.umami is None:
            return dropped
        if not (await self.consent.given(user_id) and await self.replay.given(user_id)):
            return dropped
        # Off the event loop: a batch is up to 512 KiB, and checking it is work.
        if (key := await asyncio.to_thread(unmasked, batch.events)) is not None:
            log.warning("analytics: a replay batch was dropped: %r wasn't masked", key[:40])
            return dropped
        if not inlined(batch.events, sheets or {}):
            log.warning("analytics: a replay batch was dropped: it names too many stylesheets")
            return dropped
        if not await self.umami.replay_enabled():
            # Umami's website keeps none: nothing is sent, and none is said to be recorded.
            return dropped
        if len(self.copies) >= MOST_COPIES:
            return dropped
        copy = asyncio.ensure_future(
            self._replay_copy(self.umami, self.replay, tenant, user_id, batch)
        )
        self.copies.add(copy)
        copy.add_done_callback(self.copies.discard)
        return Relayed(recorded=len(batch.events), dropped=0)

    async def _replay_copy(
        self, umami: Umami, replay: Consent, tenant: str, user_id: str, batch: ReplayBatch
    ) -> None:
        """Send Umami the replay, then read both answers again, whatever the send did."""
        await umami.record(tenant, self._person(user_id), batch.events)
        try:
            if await self.consent.given(user_id) and await replay.given(user_id):
                return
            await self.settle_replay(user_id, await replay.owe(user_id))
        except Exception as error:  # The copy is never the request's: it is said, and owed.
            log.warning("analytics: a replay's copy couldn't be checked: %s", type(error).__name__)
            try:
                await replay.owe(user_id)
            except Exception as owing:  # Nothing more can be done: said, for operators.
                log.error("analytics: a deletion couldn't be owed: %s", type(owing).__name__)

    async def settle(self, user_id: str, debt: int, *, paced: bool = True) -> bool:
        """Delete the person's events, for deletion `debt`: whether it was done.

        Undone, it stays owed. Done, it clears `debt` alone: a newer deletion, owed for events
        written since this one began, stays owed. A person's own requests set off at most so many
        deletions an hour (`paced`); past it, the background pass, which isn't paced, settles it.
        """
        if paced and self.deletes.spend(user_id, 1) is not None:
            return False
        if not await self.analytics.forget(user_id):
            return False
        if self.umami is not None and not await self.umami.forget(self._person(user_id)):
            return False
        await self.consent.settled(user_id, debt)
        return True

    async def settle_owed(self, *, most: int = 100) -> int:
        """Delete the events owed deletion, in turn: how many deletions were done.

        At most `most` people's, and at most `most` removals'. First it owes each removal in
        grantr's audit log that it hasn't read: at most `most` entries of a tenant's log.

        Every replica runs it, now and then: two may delete the same person's events, which does
        no harm, since a deletion done twice deletes nothing more.
        """
        done = 0
        for user_id, debt in await self.consent.owing(most):
            done += await self.settle(user_id, debt, paced=False)
        if self.grants is not None:
            await self._owe_removals(self.grants, most)
        ripe = datetime.now(UTC) - REMOVAL_GRACE
        for user_id, tenant, removed_at in await self.consent.removals_owed(most, before=ripe):
            done += await self._forget_removed(user_id, tenant, removed_at)
        if self.replay is not None:
            for user_id, debt in await self.replay.owing(most):
                done += await self.settle_replay(user_id, debt)
        return done

    async def _owe_removals(self, grants: Grants, most: int) -> None:
        """Owe the deletion of each person removed from a tenant, as the tenant's log says.

        A tenant whose log can't be read is said, by its id and its error's type, and skipped:
        the others are read, and the deletions ripe are done, all the same.
        """
        try:
            tenants = await grants.served_tenants()
        except Exception as error:  # Nor do the tenants' names, if they can't be read.
            log.error("analytics: the tenants weren't listed: %s", type(error).__name__)
            return
        for tenant in tenants:
            try:
                await self._owe_tenants_removals(grants, tenant, most)
            except Exception as error:  # One tenant's log never holds up the rest.
                log.error(
                    "analytics: tenant %s's removals weren't read: %s", tenant, type(error).__name__
                )

    async def _owe_tenants_removals(self, grants: Grants, tenant: str, most: int) -> None:
        """Read the tenant's log on from where it was read last, and owe what it says.

        The mark moves only once its entries are owed, so a pass that stops partway reads them
        again. A removal is owed up to its entry's time.
        """
        entries = await grants.served_audit(
            tenant, after_seq=await self.consent.audit_cursor(tenant), limit=most, keep=REMOVALS
        )
        for entry in entries:
            if isinstance(entry.event, MemberRemoved) and isinstance(entry.event.member, User):
                await self.consent.owe_removal(entry.event.member.id, tenant, entry.at)
        if entries:
            await self.consent.advance_audit(tenant, entries[-1].seq)

    async def _forget_removed(self, user_id: str, tenant: str, removed_at: datetime) -> bool:
        until = removed_at + REMOVAL_MARGIN
        if not await self.analytics.forget_in(tenant, user_id, until):
            return False
        # The tenant's session alone in Umami, found by the tenant's hash: the person's others
        # stay (portalr ADR-0076).
        if self.umami is not None and not await self.umami.forget(self._person(user_id), tenant):
            return False
        await self.consent.removal_settled(user_id, tenant, removed_at)
        return True

    async def record(self, tenant: str, user_id: str, batch: Batch, session_id: str) -> Relayed:
        """Keep the person's batch as the registry says, if they have said yes.

        A no that lands while the batch is written deletes it too: the answer is read again
        after the write, and if it is no longer yes, a new deletion is owed and tried, without
        touching the answer itself.
        """
        if not await self.consent.given(user_id):
            await self.settle_if_owed(user_id)
            return Relayed(recorded=0, dropped=len(batch.events))
        named = [
            (event.event, kept(event, REGISTRY[event.event]))
            for event in batch.events
            if event.event in REGISTRY
        ]
        written = bool(named) and await self.analytics.capture_many(
            tenant, user_id, named, session_id=session_id
        )
        if written and not await self.consent.given(user_id):
            await self.settle(user_id, await self.consent.owe(user_id))
            return Relayed(recorded=0, dropped=len(batch.events))
        recorded = len(named) if written else 0
        if written and self.umami is not None and len(self.copies) < MOST_COPIES:
            # A copy for Umami, of what was kept, after the yes was read again: never the record,
            # and never waited on, so Umami down slows no request.
            copy = asyncio.ensure_future(self._copy(self.umami, tenant, user_id, named))
            self.copies.add(copy)
            copy.add_done_callback(self.copies.discard)
        return Relayed(recorded=recorded, dropped=len(batch.events) - recorded)

    async def _copy(
        self, umami: Umami, tenant: str, user_id: str, named: list[tuple[str, dict[str, str]]]
    ) -> None:
        """Send Umami its copy, then read the person's answer again, whatever the send did.

        Any event of it may have made a session, so a no that landed meanwhile owes a deletion,
        tried at once, as a batch written while a no lands is in ClickHouse. If the answer can't
        be read again, a deletion is owed anyway: the background pass settles it.
        """
        await umami.send(tenant, self._person(user_id), named)
        try:
            if await self.consent.given(user_id):
                return
            await self.settle(user_id, await self.consent.owe(user_id))
        except Exception as error:  # The copy is never the request's: it is said, and owed.
            log.warning("analytics: Umami's copy couldn't be checked: %s", type(error).__name__)
            try:
                await self.consent.owe(user_id)
            except Exception as owing:  # Nothing more can be done: said, for operators.
                log.error("analytics: a deletion couldn't be owed: %s", type(owing).__name__)

    def _person(self, user_id: str) -> str:
        """A person as Umami knows them: the deployment's keyed hash, as ClickHouse does."""
        return distinct_id(self.analytics.key, user_id)

    async def settle_if_owed(self, user_id: str) -> None:
        """Try again a deletion owed the person, on their next request."""
        debt = await self.consent.owes(user_id)
        if debt is not None:
            await self.settle(user_id, debt)


def kept(event: Event, allowed: dict[str, frozenset[str] | None]) -> dict[str, str]:
    """An event's props as recorded: the registry's keys and values, and the app's routes."""
    props = {
        key: value
        for key, value in event.props.items()
        if key != "route" and (values := allowed.get(key)) is not None and value in values
    }
    if "route" in allowed and event.route is not None and event.route in ROUTES:
        props["route"] = event.route
    return props
