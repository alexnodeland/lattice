"""The REST surface's OpenAPI document, as an application mounting the router serves it.

``python -m reflexr.fastapi.openapi`` prints it; ``moon run reflexr:schema`` writes it to
``schemas/reflexr.openapi.json``, which a test holds to the router. The router is mounted at the
root, since each application chooses its own prefix: oncall's is ``/v1``.
"""

import json
import sys
from typing import Any

from fastapi import FastAPI
from starlette.requests import HTTPConnection

from reflexr.core import Actor, TenantId
from reflexr.fastapi.router import Unauthorized, reflexr_router
from reflexr.workspace import InMemoryStorage, Workspaces


async def _nobody(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    raise Unauthorized


def openapi_app() -> FastAPI:
    """A bare application that mounts only the router, and admits no one."""
    app = FastAPI(title="reflexr", version="1")
    app.include_router(reflexr_router(Workspaces(InMemoryStorage()), resolve_actor=_nobody))
    return app


def openapi_document() -> dict[str, Any]:
    """The document :func:`openapi_app` serves."""
    return openapi_app().openapi()


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
