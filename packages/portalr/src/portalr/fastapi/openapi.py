"""portalr's OpenAPI document, as an application mounting the router serves it.

``python -m portalr.fastapi.openapi`` prints it; ``moon run portalr:schema`` writes it to
``schemas/portalr.openapi.json``, which a test holds to the router.
"""

import json
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr.fastapi import Caller, Unauthorized
from grantr.grants import Grants, InMemoryStorage
from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay, Umami
from portalr.fastapi.router import portalr_router
from portalr.fastapi.site import Site
from portalr.readers import (
    Analytics,
    Grafana,
    Langfuse,
    LiteLLM,
    Loki,
    Prometheus,
    Readers,
    Tempo,
)

PREFIX = "/portalr"
"""Where applications mount the router."""


async def _nobody(_connection: HTTPConnection) -> Caller:
    raise Unauthorized


async def _no_invite(_email: str) -> str:
    raise NotImplementedError


async def _no_one(_ids: Collection[str]) -> dict[str, str]:
    raise NotImplementedError


def openapi_app() -> FastAPI:
    """A bare application that mounts only the router, with every tool, and admits no caller."""
    app = FastAPI(title="portalr", version="1")
    analytics = Analytics("http://clickhouse", b"key")
    readers = Readers(
        tempo=Tempo("http://tempo"),
        loki=Loki("http://loki"),
        prometheus=Prometheus("http://prom-label-proxy"),
        langfuse=Langfuse("http://langfuse", project="project"),
        litellm=LiteLLM("http://litellm"),
        grafana=Grafana("http://grafana"),
        analytics=analytics,
    )
    relay = Relay(
        analytics,
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=Umami("http://umami", "website", "password"),
        replay=InMemoryConsent(),
    )
    router = portalr_router(
        resolve_actor=_nobody,
        grants=Grants(InMemoryStorage()),
        readers=readers,
        invite=_no_invite,
        people=_no_one,
        relay=relay,
        site=Site(supabase_url="http://supabase", supabase_key="publishable"),
        ui=Path("static"),
    )
    app.include_router(router, prefix=PREFIX)
    return app


def openapi_document() -> dict[str, Any]:
    """The document :func:`openapi_app` serves."""
    return openapi_app().openapi()


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
