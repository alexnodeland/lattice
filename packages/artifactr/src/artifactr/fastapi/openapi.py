"""The REST surface's OpenAPI document, as an application mounting the router serves it.

``python -m artifactr.fastapi.openapi`` prints it; ``moon run artifactr:schema`` writes it to
``schemas/artifactr.openapi.json``, which a test holds to the router. The router is mounted at
the root, since each application chooses its own prefix: docplan's is ``/v1``.
"""

import json
import sys
from typing import Any

from fastapi import FastAPI
from pydantic_ai import Agent
from starlette.requests import HTTPConnection

from artifactr.agent import Runner, Session
from artifactr.core import Actor, TenantId
from artifactr.fastapi.router import Unauthorized, artifactr_router
from artifactr.workspace import InMemoryStorage, Workspaces


async def _nobody(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    raise Unauthorized


def openapi_app() -> FastAPI:
    """A bare application that mounts only the router, and admits no one.

    Its runner's agent never runs: no request gets past authentication to start a turn.
    """
    app = FastAPI(title="artifactr", version="1")
    runner = Runner(Agent("test", deps_type=Session[None]), app=None)
    app.include_router(
        artifactr_router(Workspaces(InMemoryStorage()), runner, resolve_actor=_nobody)
    )
    return app


def openapi_document() -> dict[str, Any]:
    """The document :func:`openapi_app` serves."""
    return openapi_app().openapi()


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
