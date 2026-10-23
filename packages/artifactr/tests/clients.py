"""HTTP clients for the tests' ASGI apps, each entered, so all its requests share one event loop.

A `TestClient` that isn't entered runs each request on an event loop of its own, in a thread of
its own. The in-memory stores' locks are asyncio's, so two such requests at once can leave one
waiting on a lock it is never woken from (#594). `entered` enters a client, and the test leaves it
as it ends; `tests/conftest.py` refuses a request through a client that wasn't entered.
"""

import contextlib

from starlette.testclient import TestClient
from starlette.types import ASGIApp

OPEN = contextlib.ExitStack()
"""The clients the running test entered, which it leaves as it ends."""


def entered(app: ASGIApp) -> TestClient:
    """A client for the app, entered until the test ends."""
    return OPEN.enter_context(TestClient(app))
