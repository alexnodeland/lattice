"""Check portalr's Umami against a running stack's: a session per person, and deletion by person.

stackr's smoke test runs this with its umami profile (stackr ADR-0050, portalr ADR-0076). It sends
two people's events to Umami's ingest, as portalr's relay does; finds each person's session, one
of their own; deletes the first's; and fails unless the second's survives. With ClickHouse named
too, it runs portalr's relay itself, end to end: a person's yes sends their events to both, and
their no deletes them from both.

Usage: scripts/smoke_umami.py   (from portalr's directory)

Every address and password comes from the environment, never the arguments: PORTALR_UMAMI_URL,
UMAMI_WEBSITE_ID and UMAMI_PORTALR_PASSWORD; and, for the relay, PORTALR_CLICKHOUSE_URL and
CLICKHOUSE_ANALYTICS_WRITER_PASSWORD.
"""

import asyncio
import os
import secrets
import sys

import httpx

from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay, Umami
from portalr.analytics.relay import Batch, Event
from portalr.readers import Analytics
from portalr.readers.analytics import distinct_id


def say(message: str) -> None:
    """Report a line, as stackr's smoke test does."""
    sys.stderr.write(f"{message}\n")


async def main() -> int:
    """Two people in Umami, one deleted; then the relay, with ClickHouse; 0 if all held."""
    umami = Umami(
        os.environ["PORTALR_UMAMI_URL"],
        os.environ["UMAMI_WEBSITE_ID"],
        os.environ["UMAMI_PORTALR_PASSWORD"],
        httpx.AsyncClient(),
    )
    # A tenant no deployment has, so what this sends is plainly the smoke test's to operators.
    tenant = f"stackr-smoke-{secrets.token_hex(4)}"
    first, second = secrets.token_hex(16), secrets.token_hex(16)
    for person in (first, second):
        if not await umami.send(tenant, person, [("app.page.viewed.v1", {"route": "/"})] * 2):
            say(f"FAIL: Umami didn't take {person}'s events")
            await umami.client.aclose()
            return 1
    status = 0
    held = {person: await umami.sessions(person) for person in (first, second)}
    if all(len(found) == 1 for found in held.values()) and held[first] != held[second]:
        say("ok: Umami keeps each person's events in a session of their own")
    else:
        say(f"FAIL: Umami's sessions for two people: {held}")
        status = 1
    if not await umami.forget(first):
        say("FAIL: Umami didn't delete a person's sessions")
        await umami.client.aclose()
        return 1
    left = {person: len(await umami.sessions(person)) for person in (first, second)}
    if left == {first: 0, second: 1}:
        say("ok: deleting a person in Umami deletes theirs alone")
    else:
        say(f"FAIL: after deleting {first}, Umami has {left}")
        status = 1
    await umami.forget(second)
    clickhouse = os.environ.get("PORTALR_CLICKHOUSE_URL")
    if clickhouse:
        status |= await relayed(umami, clickhouse, tenant)
    await umami.client.aclose()
    return status


async def relayed(umami: Umami, clickhouse: str, tenant: str) -> int:
    """Portalr's relay, end to end: a yes copies a batch to Umami, and a no deletes it there."""
    writer = httpx.AsyncClient(
        auth=("portalr_analytics_writer", os.environ["CLICKHOUSE_ANALYTICS_WRITER_PASSWORD"])
    )
    key = secrets.token_bytes(32)
    relay = Relay(
        Analytics(clickhouse, key, writer=writer),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=umami,
    )
    user = f"smoke-person-{secrets.token_hex(4)}"
    person = distinct_id(key, user)
    await relay.answer(user, yes=True)
    batch = Batch(session="smoke", events=[Event(event="app.page.viewed.v1", route="/")])
    relayed = await relay.record(tenant, user, batch, "smoke")
    await asyncio.gather(*relay.copies)
    status = 0
    if relayed.recorded == 1 and len(await umami.sessions(person)) == 1:
        say("ok: portalr's relay sends a person's yes to ClickHouse and a copy to Umami")
    else:
        say(f"FAIL: portalr's relay, with a yes: {relayed}")
        status = 1
    said = await relay.answer(user, yes=False)
    if said.deleted and await umami.sessions(person) == []:
        say("ok: a person's no deletes their copy in Umami too")
    else:
        say(f"FAIL: portalr's relay, with a no: {said}")
        status = 1
    await writer.aclose()
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
