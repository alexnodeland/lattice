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
import secrets
import time
from dataclasses import dataclass, field
from importlib import resources
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from portalr.analytics.consent import Consent
from portalr.analytics.limiter import InMemoryRateLimiter, RateLimiter
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
    umami: Umami | None = None
    """Umami, sent a copy of each consented event, for operators' journeys (portalr ADR-0076);
    a person's deletion deletes their sessions there too."""
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
        return Answered(given=False, deleted=await self.settle(user_id, debt) if debt else None)

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
        """Delete the events of at most `most` people a deletion is owed, in turn: how many.

        Every replica runs it, now and then: two may delete the same person's events, which does
        no harm, since a deletion done twice deletes nothing more.
        """
        done = 0
        for user_id, debt in await self.consent.owing(most):
            done += await self.settle(user_id, debt, paced=False)
        return done

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
        if written and self.umami is not None:
            # A copy for Umami, of what was kept, after the yes was read again: never the record,
            # and never waited on, so Umami down slows no request.
            copy = asyncio.ensure_future(self._copy(self.umami, tenant, user_id, named))
            self.copies.add(copy)
            copy.add_done_callback(self.copies.discard)
        return Relayed(recorded=recorded, dropped=len(batch.events) - recorded)

    async def _copy(
        self, umami: Umami, tenant: str, user_id: str, named: list[tuple[str, dict[str, str]]]
    ) -> None:
        """Send Umami its copy: a no that lands while it is sent deletes it there too.

        As a no that lands while a batch is written does in ClickHouse: owed, and tried at once.
        """
        sent = await umami.send(tenant, self._person(user_id), named)
        if sent and not await self.consent.given(user_id):
            await self.settle(user_id, await self.consent.owe(user_id))

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
