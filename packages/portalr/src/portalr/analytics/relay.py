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

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from importlib import resources
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from portalr.analytics.consent import Consent
from portalr.analytics.limiter import RateLimiter
from portalr.readers.analytics import Analytics

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

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: Annotated[str, StringConstraints(max_length=64)]
    route: Short | None = None
    props: Annotated[
        dict[Annotated[str, StringConstraints(max_length=64)], Short], Field(max_length=10)
    ] = {}


class Batch(BaseModel):
    """A browser's events, in the session portalr signed for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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

    model_config = ConfigDict(frozen=True, extra="forbid")

    given: bool


class Answered(Answer):
    """A person's answer, recorded; on a no, whether their events were deleted."""

    deleted: bool | None = None


@dataclass(frozen=True)
class Relay:
    """What the relay needs: the analytics store, people's answers, and their pace.

    Args:
        analytics: ClickHouse's analytics, with the deployment's key.
        consent: People's answers, in the application's database.
        limiter: How fast a person may send events.
    """

    analytics: Analytics
    consent: Consent
    limiter: RateLimiter

    def sign(self, user_id: str, *, now: float | None = None) -> str:
        """A new session id for the person, signed so no one else can send under it."""
        nonce = f"{int(now if now is not None else time.time())}-{secrets.token_hex(8)}"
        return f"{nonce}.{self._signature(user_id, nonce)}"

    def session_of(self, user_id: str, signed: str, *, now: float | None = None) -> str | None:
        """The session id a signed one names, if it is the person's and still fresh; else None."""
        nonce, _, signature = signed.partition(".")
        if not hmac.compare_digest(signature, self._signature(user_id, nonce)):
            return None
        started, _, _ = nonce.partition("-")
        age = (now if now is not None else time.time()) - int(started)
        return nonce if 0 <= age < SESSION_HOURS * 3600 else None

    def _signature(self, user_id: str, nonce: str) -> str:
        message = f"session\0{user_id}\0{nonce}".encode()
        return hmac.new(self.analytics.key, message, hashlib.sha256).hexdigest()[:32]


def kept(event: Event, allowed: frozenset[str]) -> dict[str, str]:
    """An event's props as recorded: the registry's keys, the app's routes, and no email."""
    props = {k: v for k, v in event.props.items() if k in allowed and k != "route" and "@" not in v}
    if "route" in allowed and event.route is not None and event.route in ROUTES:
        props["route"] = event.route
    return props
