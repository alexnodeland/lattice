"""The check-out routes' OpenAPI document, as an application mounting the router serves it.

``python -m artifactr.files.fastapi.openapi`` prints it; ``moon run artifactr:schema`` writes it
to ``schemas/artifactr-files.openapi.json``, which a test holds to the router.
"""

import json
import sys
from typing import Any

from fastapi import FastAPI
from starlette.requests import HTTPConnection

from artifactr.core import Actor, TenantId
from artifactr.fastapi import Unauthorized
from artifactr.files.app import FakeApp
from artifactr.files.blobs import InMemoryBlobs
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.fastapi.router import files_router
from artifactr.files.native import NativeFiles
from artifactr.workspace import InMemoryStorage, Workspaces


async def _nobody(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    raise Unauthorized


def openapi_app() -> FastAPI:
    """A bare application that mounts only the router, over the fake app, and admits no one."""
    app = FastAPI(title="artifactr files", version="1")
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    app.include_router(files_router(Workspaces(InMemoryStorage()), files, resolve_actor=_nobody))
    return app


def openapi_document() -> dict[str, Any]:
    """The document :func:`openapi_app` serves."""
    return openapi_app().openapi()


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
