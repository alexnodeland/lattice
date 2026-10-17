"""The trackers' webhooks' route: a verified nudge is 204, anything else gives nothing away."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from relayr.fastapi import MAX_BODY, tracker_router
from relayr.ledger import Ledger
from tests.clock import FakeClock
from tests.trackers.conftest import TENANT
from tests.trackers.following import Following, following
from tests.trackers.test_following import nudge

ROUTE = f"/relayr/v1/trackers/{TENANT}/fake"


@pytest.fixture
async def app(ledger: Ledger, clock: FakeClock) -> Following:
    made = following(ledger, clock)
    assert await made.poll(), "its credentials are read, as a follower's poll reads them"
    return made


@pytest.fixture
async def client(app: Following) -> AsyncIterator[httpx.AsyncClient]:
    server = FastAPI()
    server.include_router(tracker_router(app.followers))
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://relayr.test") as made:
        yield made


async def test_a_verified_nudge_is_accepted(client: httpx.AsyncClient) -> None:
    headers, body = nudge()
    response = await client.post(ROUTE, headers=headers, content=body)
    assert (response.status_code, response.content) == (204, b"")


async def test_an_unknown_tenant_and_a_bad_signature_are_the_same_refusal(
    client: httpx.AsyncClient,
) -> None:
    headers, body = nudge()
    unknown = await client.post("/relayr/v1/trackers/globex/fake", headers=headers, content=body)
    forged = await client.post(ROUTE, headers=nudge(secret="forged")[0], content=body)
    assert unknown.status_code == forged.status_code == 401
    assert unknown.json() == forged.json() == {"detail": "the webhook did not verify"}


async def test_a_body_too_large_is_refused_before_it_is_read(client: httpx.AsyncClient) -> None:
    headers, _ = nudge()
    declared = await client.post(ROUTE, headers=headers, content=b"x" * (MAX_BODY + 1))
    assert declared.status_code == 413

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"x" * (MAX_BODY // 2)

    streamed = await client.post(ROUTE, headers=headers, content=chunks())
    assert streamed.status_code == 413
