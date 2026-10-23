"""A request's analytics session, on its server span: how a trace links to a session (ADR-0073).

The browser of a person who said yes sends the session id portalr signed for them in
``X-Portalr-Analytics-Session``, with every request it makes to the application. ``SessionStamp``
reads it, and only then asks the application's own resolver who the caller is. Where the value
is that person's own session, signed by portalr and still fresh, and they still say yes, it sets
the session's id on the request's server span, as ``portalr.analytics.session``.

The stamp never changes the request. Any failure leaves the span as it was and the request goes
on: no header, a caller the resolver doesn't know or a key's, a value forged, another person's,
expired or bare, a person who said no, or a resolver or a consent that fails. The header's value
is never logged.
"""

import contextlib
from typing import Final

from opentelemetry import trace
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from grantr.core import User
from grantr.fastapi import ResolveActor
from portalr.analytics.relay import Relay

HEADER: Final = b"x-portalr-analytics-session"
"""The header a person's browser sends their signed session in."""

ATTRIBUTE: Final = "portalr.analytics.session"
"""The server span attribute that names the request's analytics session: an id portalr made at
random, of no one, which only the session's own events share."""

MOST_LENGTH: Final = 128
"""The longest value read: a signed session is about 80 characters."""


class SessionStamp:
    """ASGI middleware: the request's analytics session, on its server span, where it is valid.

    Installed inside the server's instrumentation, so the span it stamps is the request's own.

    Args:
        app: The application it wraps.
        relay: The relay that signed the session, with people's answers.
        resolve_actor: The application's own resolver of a request's caller.
    """

    def __init__(self, app: ASGIApp, *, relay: Relay, resolve_actor: ResolveActor) -> None:
        self.app = app
        self.relay = relay
        self.resolve_actor = resolve_actor

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Stamp the request's server span where its session is valid, then serve it as it came."""
        if scope["type"] == "http":
            signed = dict(scope["headers"]).get(HEADER)
            if signed is not None:
                # A stamp that fails for any reason is no stamp; the request goes on as it came.
                with contextlib.suppress(Exception):
                    await self._stamp(scope, signed)
        await self.app(scope, receive, send)

    async def _stamp(self, scope: Scope, signed: bytes) -> None:
        span = trace.get_current_span()
        if not span.is_recording() or len(signed) > MOST_LENGTH:
            return
        who = await self.resolve_actor(HTTPConnection(scope))
        if not isinstance(who.subject, User):
            return
        session = self.relay.session_of(who.subject.id, signed.decode("ascii"))
        if session is not None and await self.relay.consent.given(who.subject.id):
            span.set_attribute(ATTRIBUTE, session)
