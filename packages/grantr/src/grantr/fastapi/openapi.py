"""The admin API's OpenAPI document, as an application mounting the router serves it.

``python -m grantr.fastapi.openapi`` prints it; ``moon run grantr:schema`` writes it to
``schemas/grantr.openapi.json``, which a test holds to the router.
"""

import json
import sys
from typing import Any

from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr.fastapi.router import Caller, Unauthorized, grantr_router
from grantr.grants import Grants, InMemoryStorage

PREFIX = "/grantr/v1"
"""Where applications mount the router."""


async def _nobody(_connection: HTTPConnection) -> Caller:
    raise Unauthorized


def openapi_app() -> FastAPI:
    """A bare application that mounts only the router, and admits no caller."""
    app = FastAPI(title="grantr", version="1")
    app.include_router(
        grantr_router(Grants(InMemoryStorage()), resolve_actor=_nobody), prefix=PREFIX
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
