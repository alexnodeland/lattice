"""Check portalr's Langfuse and LiteLLM readers against a running stack: each answers ``ok``.

The Acceptance job runs neither tool (portalr ADR-0011), so stackr's smoke test runs this beside
both. It sends Langfuse a trace over OpenTelemetry, tagged as the libraries tag theirs, and a score
on it, then reads the tenant's scores, its spend and every tenant's spend through portalr's readers.
The tenant's LiteLLM team, ``tenant-<TENANT>``, must exist already, as the smoke test's does.

Usage: scripts/smoke_readers.py TENANT   (from portalr's directory)

The tools' URLs and keys come from the environment, never the arguments: PORTALR_LANGFUSE_URL,
LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, PORTALR_LITELLM_URL and LITELLM_MASTER_KEY.
"""

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from portalr.readers import Langfuse, LiteLLM, Ok, Window
from portalr.readers.langfuse import tenant_tag
from portalr.tenant import allowed

SCORE = "portalr-smoke"
TIMEOUT = 240
"""Seconds to wait for the score: Langfuse's score API may lag its ingestion by minutes."""


def say(message: str) -> None:
    """Report a line, as stackr's smoke test does."""
    sys.stderr.write(f"{message}\n")


async def scored(langfuse: Langfuse, tenant: str) -> bool:
    """Score a trace tagged for the tenant, as the libraries tag theirs, and find the score."""
    trace, span, now = uuid.uuid4().hex, uuid.uuid4().hex[:16], datetime.now(UTC)
    nanos = str(int(now.timestamp() * 1e9))
    tags = {"arrayValue": {"values": [{"stringValue": tenant_tag(allowed(tenant))}]}}
    spans = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": SCORE}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace,
                                "spanId": span,
                                "name": SCORE,
                                "kind": 1,
                                "startTimeUnixNano": nanos,
                                "endTimeUnixNano": nanos,
                                "attributes": [{"key": "langfuse.trace.tags", "value": tags}],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    sent = await langfuse.client.post(f"{langfuse.url}/api/public/otel/v1/traces", json=spans)
    sent.raise_for_status()
    score = {"traceId": trace, "name": SCORE, "value": 1, "dataType": "NUMERIC"}
    sent = await langfuse.client.post(f"{langfuse.url}/api/public/scores", json=score)
    sent.raise_for_status()
    window = Window(start=now - timedelta(hours=1), end=now + timedelta(minutes=10))
    answer = await langfuse.scores(allowed(tenant), window)
    for _ in range(TIMEOUT // 3):
        if isinstance(answer, Ok) and any(score.trace_id == trace for score in answer.data.scores):
            return True
        await asyncio.sleep(3)
        answer = await langfuse.scores(allowed(tenant), window)
    say(f"FAIL: portalr's Langfuse reader never found the score: {answer}")
    return False


async def spent(litellm: LiteLLM, tenant: str) -> bool:
    """Read the tenant's team, and every team, through the reader."""
    mine = await litellm.spend(allowed(tenant))
    if not isinstance(mine, Ok) or mine.data is None:
        say(f"FAIL: portalr's LiteLLM reader didn't read {tenant}'s team: {mine}")
        return False
    every = await litellm.every_tenant()
    if not isinstance(every, Ok) or tenant not in {team.tenant for team in every.data}:
        say(f"FAIL: portalr's LiteLLM reader didn't list {tenant}'s team: {every}")
        return False
    return True


async def main(tenant: str) -> int:
    """Run both checks, and say how each went."""
    env = os.environ
    keys = env["LANGFUSE_PUBLIC_KEY"], env["LANGFUSE_SECRET_KEY"]
    master = {"Authorization": f"Bearer {env['LITELLM_MASTER_KEY']}"}
    async with (
        httpx.AsyncClient(auth=keys) as langfuse_client,
        httpx.AsyncClient(headers=master) as litellm_client,
    ):
        langfuse = Langfuse(env["PORTALR_LANGFUSE_URL"], project="smoke", client=langfuse_client)
        litellm = LiteLLM(env["PORTALR_LITELLM_URL"], client=litellm_client)
        results = {
            "portalr's Langfuse reader reads the tenant's scores": await scored(langfuse, tenant),
            "portalr's LiteLLM reader reads the tenant's spend": await spent(litellm, tenant),
        }
    for check, passed in results.items():
        if passed:
            say(f"ok: {check}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
