"""A request's analytics session on its server span: stamped only where it is the caller's own."""

import logging
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.requests import HTTPConnection
from starlette.types import Message, Receive, Scope, Send

from grantr.core import ServicePrincipal, User
from grantr.fastapi import Caller, Unauthorized
from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay, SessionStamp
from portalr.analytics.stamp import ATTRIBUTE, HEADER
from portalr.readers import Analytics

KEY = b"the deployment's key"
ROUTES = ("/artifactr/v1/threads", "/portalr/v1/config.json")
"""A library's route and portalr's: the stamp is the application's, not one router's."""


class Resolver:
    """The application's resolver, as a test sets it: a person by their bearer, or a failure."""

    def __init__(self) -> None:
        self.asked = 0
        self.fails: Exception | None = None

    async def __call__(self, connection: HTTPConnection) -> Caller:
        self.asked += 1
        if self.fails is not None:
            raise self.fails
        bearer = connection.headers.get("authorization", "").removeprefix("Bearer ")
        if bearer.startswith("key-"):
            return Caller(ServicePrincipal(id="bot"), "acme")
        if not bearer:
            raise Unauthorized("no caller")
        return Caller(User(id=bearer))


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


class Consent(InMemoryConsent):
    """People's answers, which a test can make fail."""

    fails = False

    async def given(self, user_id: str) -> bool:
        if self.fails:
            raise RuntimeError(user_id)
        return await super().given(user_id)


@pytest.fixture
def consent() -> Consent:
    return Consent()


@pytest.fixture
def relay(consent: Consent) -> Relay:
    return Relay(Analytics("http://clickhouse:8123", KEY), consent, InMemoryRateLimiter())


@pytest.fixture
def resolver() -> Resolver:
    return Resolver()


@pytest.fixture
def client(
    exporter: InMemorySpanExporter, relay: Relay, resolver: Resolver
) -> Iterator[httpx.AsyncClient]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI()
    for route in ROUTES:
        app.add_api_route(route, lambda: {"ok": True})
    # As the template installs it: added before the server's instrumentation, so it runs inside.
    app.add_middleware(SessionStamp, relay=relay, resolve_actor=resolver)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://app")
    FastAPIInstrumentor.uninstrument_app(app)


def stamped(exporter: InMemorySpanExporter) -> list[object]:
    """The session each server span carries, None where it has none, the latest last."""
    servers = [s for s in exporter.get_finished_spans() if s.kind.name == "SERVER"]
    return [(s.attributes or {}).get(ATTRIBUTE) for s in servers]


async def ask(
    client: httpx.AsyncClient, route: str, user: str, session: str | bytes | None
) -> None:
    headers = [(b"authorization", f"Bearer {user}".encode())] if user else []
    if session is not None:
        headers.append((HEADER, session if isinstance(session, bytes) else session.encode()))
    response = await client.get(route, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize("route", ROUTES)
async def test_a_persons_own_fresh_session_is_on_the_server_span(
    client: httpx.AsyncClient, exporter: InMemorySpanExporter, relay: Relay, route: str
) -> None:
    await relay.consent.give("alice", yes=True)
    signed = relay.sign("alice")
    await ask(client, route, "alice", signed)
    assert stamped(exporter) == [signed.partition(".")[0]]


async def test_without_the_header_the_caller_isnt_resolved(
    client: httpx.AsyncClient, exporter: InMemorySpanExporter, resolver: Resolver
) -> None:
    await ask(client, ROUTES[0], "alice", None)
    assert resolver.asked == 0
    assert stamped(exporter) == [None]


async def test_no_stamp_for_anything_but_the_callers_own_valid_fresh_session(
    client: httpx.AsyncClient,
    exporter: InMemorySpanExporter,
    relay: Relay,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await relay.consent.give("alice", yes=True)
    await relay.consent.give("bob", yes=True)
    signed = relay.sign("alice")
    nonce, _, signature = signed.partition(".")
    tried = {
        "forged": f"{nonce}.{'0' * len(signature)}",
        "another person's": relay.sign("bob"),
        "expired": relay.sign("alice", now=0),
        "bare": nonce,
        "too long": signed + "x" * 200,
        "not ascii": "é".encode() * 4,
    }
    caplog.set_level(logging.DEBUG)
    for value in tried.values():
        await ask(client, ROUTES[0], "alice", value)
    assert stamped(exporter) == [None] * len(tried)
    assert not any(str(value) in caplog.text for value in tried.values() if value)
    assert signature not in caplog.text


async def test_no_stamp_for_a_key_an_unknown_caller_or_a_person_who_said_no(
    client: httpx.AsyncClient, exporter: InMemorySpanExporter, relay: Relay
) -> None:
    signed = relay.sign("alice")
    await ask(client, ROUTES[0], "alice", signed)  # alice never said yes
    await ask(client, ROUTES[0], "key-1", relay.sign("bot"))
    await ask(client, ROUTES[0], "", signed)
    assert stamped(exporter) == [None, None, None]


async def test_a_resolver_or_consent_that_fails_leaves_the_request_and_the_span_alone(
    client: httpx.AsyncClient,
    exporter: InMemorySpanExporter,
    relay: Relay,
    resolver: Resolver,
    consent: Consent,
) -> None:
    await consent.give("alice", yes=True)
    signed = relay.sign("alice")
    resolver.fails = RuntimeError("the token service is down")
    await ask(client, ROUTES[0], "alice", signed)
    resolver.fails = None

    consent.fails = True
    await ask(client, ROUTES[0], "alice", signed)
    assert stamped(exporter) == [None, None]


async def test_anything_but_a_request_passes_through_untouched(
    relay: Relay, resolver: Resolver
) -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(str(scope["type"]))

    async def receive() -> Message:
        return {}

    async def send(message: Message) -> None:
        pass

    stamp = SessionStamp(inner, relay=relay, resolve_actor=resolver)
    await stamp({"type": "lifespan"}, receive, send)
    await stamp({"type": "websocket", "headers": [(HEADER, b"x")]}, receive, send)
    assert seen == ["lifespan", "websocket"]
    assert resolver.asked == 0
