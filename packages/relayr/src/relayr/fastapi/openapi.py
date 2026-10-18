"""relayr's routes' OpenAPI document, as an application mounting its routers serves it.

``python -m relayr.fastapi.openapi`` prints it; ``moon run relayr:schema`` writes it to
``schemas/relayr.openapi.json``, which a test holds to the routers, and from which portalr's
client is typed. Its paths carry ``/relayr/v1`` themselves, so it is mounted at the root.
"""

import json
import sys
from typing import Any

from fastapi import FastAPI
from fastapi.requests import HTTPConnection

from reflexr.core import Actor, TenantId
from reflexr.fastapi import Unauthorized
from reflexr.workspace import InMemoryStorage, Workspaces
from relayr.fastapi.reads import tracker_reads_router
from relayr.fastapi.router import tracker_router
from relayr.ledger import InMemoryLedger
from relayr.trackers import FakeTracker, TrackerCredentials, TrackerFollowers, Trackers


async def _nobody(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    raise Unauthorized


async def no_credentials(_tenant: str) -> TrackerCredentials:
    """The credentials of the document's application, which has no tenants."""
    raise LookupError("the document's application has no tenants")


def openapi_app() -> FastAPI:
    """A bare application that mounts only relayr's routers, binds nothing and admits no one."""
    trackers = Trackers(
        InMemoryLedger(),
        connect=FakeTracker().connect,
        credentials=no_credentials,
        bindings={},
        integration="tracker:fake",
    )
    workspaces = Workspaces(InMemoryStorage())
    app = FastAPI(title="relayr", version="1")
    app.include_router(tracker_router(TrackerFollowers(trackers, workspaces)))
    app.include_router(tracker_reads_router(trackers, workspaces, resolve_actor=_nobody))
    return app


def openapi_document() -> dict[str, Any]:
    """The document :func:`openapi_app` serves."""
    return openapi_app().openapi()


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
