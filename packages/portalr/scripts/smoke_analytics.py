"""Check portalr's analytics against a running stack's ClickHouse: two tenants, each its own.

stackr's smoke test runs this with its analytics profile (lattice RFC-0008, stackr ADR-0044). It
records an event in each of two new tenants as the writer, then reads each tenant's counts and
adoption as the reader, through portalr's reader, and fails if either sees the other's.

Usage: scripts/smoke_analytics.py   (from portalr's directory)

ClickHouse's URL and the two users' passwords come from the environment, never the arguments:
PORTALR_CLICKHOUSE_URL, CLICKHOUSE_ANALYTICS_WRITER_PASSWORD and CLICKHOUSE_ANALYTICS_PASSWORD.
"""

import asyncio
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta

import httpx

from portalr.readers import Analytics, Ok
from portalr.readers.analytics import AdoptionQuery
from portalr.readers.query import Span
from portalr.tenant import allowed


def say(message: str) -> None:
    """Report a line, as stackr's smoke test does."""
    sys.stderr.write(f"{message}\n")


async def main() -> int:
    """Two tenants' events, each read back alone; 0 if neither saw the other's."""
    url = os.environ["PORTALR_CLICKHOUSE_URL"]
    writer = httpx.AsyncClient(
        auth=("portalr_analytics_writer", os.environ["CLICKHOUSE_ANALYTICS_WRITER_PASSWORD"])
    )
    reader = httpx.AsyncClient(
        auth=("portalr_analytics", os.environ["CLICKHOUSE_ANALYTICS_PASSWORD"])
    )
    try:
        pinged = (await writer.get(f"{url}/ping", timeout=10)).text.strip()
    except httpx.HTTPError as error:
        say(f"FAIL: ClickHouse at {url} didn't answer: {type(error).__name__}: {error}")
        return 1
    say(f"ok: ClickHouse at {url} answers {pinged!r}")
    analytics = Analytics(url, secrets.token_bytes(32), writer=writer, reader=reader)
    a, b = f"smoke-a-{secrets.token_hex(4)}", f"smoke-b-{secrets.token_hex(4)}"
    for tenant, times in ((a, 2), (b, 3)):
        for _ in range(times):
            if not await analytics.capture(tenant, "member.invited.v1", f"{tenant}-person"):
                say(f"FAIL: portalr's analytics didn't record an event in {tenant}")
                return 1
    now = datetime.now(UTC)
    span = Span(start=now - timedelta(hours=1), end=now + timedelta(minutes=1))
    status = 0
    for tenant, times in ((a, 2), (b, 3)):
        counts = await analytics.counts(allowed(tenant), span)
        if not isinstance(counts, Ok):
            say(f"FAIL: portalr's analytics reader, for {tenant}: {counts}")
            status = 1
            continue
        seen = [(c.event, c.count, c.people) for c in counts.data]
        if seen == [("member.invited.v1", times, 1)]:
            say(f"ok: portalr's analytics reader sees {tenant}'s {times} events, and no other's")
        else:
            say(f"FAIL: portalr's analytics reader, for {tenant}, saw {seen}")
            status = 1
    # Each tenant's adoption: a's one person, who viewed a page; b's none.
    if not await analytics.capture(a, "app.page.viewed.v1", f"{a}-person", props={"route": "/"}):
        say(f"FAIL: portalr's analytics didn't record a page view in {a}")
        return 1
    window = AdoptionQuery(start=span.start, end=span.end)
    for tenant, people, viewed in ((a, 1, 1), (b, 1, 0)):
        adoption = await analytics.adoption(allowed(tenant), window)
        if (
            isinstance(adoption, Ok)
            and adoption.data.complete
            and adoption.data.active is not None
            and adoption.data.active.window == people
            and adoption.data.funnel is not None
            and adoption.data.funnel.page == viewed
        ):
            say(f"ok: portalr's adoption read of {tenant} counts its own people alone")
        else:
            say(f"FAIL: portalr's adoption read of {tenant}: {adoption}")
            status = 1
    # Forgetting a's person, as taking back their yes does: a's reads see nothing at once.
    if not await analytics.forget(f"{a}-person"):
        say("FAIL: portalr's analytics didn't delete a person's events")
        return 1
    counts = await analytics.counts(allowed(a), span)
    if isinstance(counts, Ok) and counts.data == []:
        say(f"ok: portalr's analytics forgets {a}'s person, at once")
    else:
        say(f"FAIL: portalr's analytics, after forgetting {a}'s person, read {counts}")
        status = 1
    await writer.aclose()
    await reader.aclose()
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
