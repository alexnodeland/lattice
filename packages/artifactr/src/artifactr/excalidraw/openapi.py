"""The diagrams' image routes' OpenAPI document, as an application mounting the router serves it.

``python -m artifactr.excalidraw.openapi`` prints it; ``moon run artifactr:schema`` writes it to
``schemas/artifactr-excalidraw.openapi.json``, which a test holds to the router, and portalr's
client generates its types from.
"""

import json
import sys
from typing import Any

from fastapi import FastAPI
from starlette.requests import HTTPConnection

from artifactr.core import Actor, TenantId
from artifactr.excalidraw.fastapi import diagrams_router
from artifactr.fastapi import Unauthorized
from artifactr.files.blobs import InMemoryBlobs
from artifactr.workspace import InMemoryStorage, Workspaces


async def _nobody(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    raise Unauthorized


def openapi_app() -> FastAPI:
    """A bare application that mounts only the router, and admits no one."""
    app = FastAPI(title="artifactr diagrams", version="1")
    app.include_router(
        diagrams_router(Workspaces(InMemoryStorage()), InMemoryBlobs(), resolve_actor=_nobody)
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
